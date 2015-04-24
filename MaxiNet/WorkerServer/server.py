import atexit
import logging
import subprocess
import sys
import tempfile

from mininet.link import TCLink, TCIntf
from mininet.net import Mininet
from mininet.node import UserSwitch, OVSSwitch
import mininet.term
import Pyro4

from MaxiNet.tools import Tools
from MaxiNet.WorkerServer.ssh_manager import SSH_Manager


class WorkerServer(object):

    def __init__(self):
        self._ns = None
        self._pyrodaemon = None
        self.logger = logging.getLogger(__name__)
        self._manager = None
        self.mnManager = MininetManager()
        self.sshManager = None
        self.ssh_folder = tempfile.mkdtemp()
        logging.basicConfig(level=logging.DEBUG)
        self.ip = None
        self._shutdown = False
        #Pyro4.config.COMMTIMEOUT = 2

    def start(self, ip, port, password):
        self.logger.info("starting up and connecting to  %s:%d"
                         % (ip, port))
        #Pyro4.config.HMAC_KEY = password
        self._ns = Pyro4.locateNS(ip, port, hmac_key=password)
        self.config = Pyro4.Proxy(self._ns.lookup("config"))
        self.config._pyroHmacKey=password
        self.ip = self.config.get_worker_ip(self.get_hostname())
        if(not self.ip):
            self.ip = Tools.guess_ip()
            if not self.config.has_section(self.get_hostname()):
                self.config.add_section(self.get_hostname())
            self.config.set(self.get_hostname(), "ip", self.ip)
            self.logger.warn("""FrontendServer did not know IP of this host.
                             Guessed: %s""" % self.ip)
        self.logger.info("configuring and starting ssh daemon...")
        self.sshManager = SSH_Manager(folder=self.ssh_folder, ip=self.ip, port=self.config.get_sshd_port(), user=self.config.get("all", "sshuser"))
        self.sshManager.start_sshd()
        self._pyrodaemon = Pyro4.Daemon(host=self.ip)
        self._pyrodaemon._pyroHmacKey=password
        uri = self._pyrodaemon.register(self)
        self._ns.register(self._get_pyroname(), uri)
        uri = self._pyrodaemon.register(self.mnManager)
        self._ns.register(self._get_pyroname()+".mnManager", uri)
        uri = self._pyrodaemon.register(self.sshManager)
        self._ns.register(self._get_pyroname()+".sshManager", uri)
        atexit.register(self._stop)
        self.logger.info("looking for manager application...")
        manager_uri = self._ns.lookup("MaxiNetManager")
        if(manager_uri):
            self._manager = Pyro4.Proxy(manager_uri)
            self._manager._pyroHmacKey=password
            self.logger.info("signing in...")
            if(self._manager.worker_signin(self._get_pyroname(), self.get_hostname())):
                self.logger.info("done. Entering requestloop.")
                self._started = True
                self._pyrodaemon.requestLoop()
            else:
                self.logger.error("signin failed.")
        else:
            self.logger.error("no manager found.")

    def _get_pyroname(self):
        return "MaxiNetWorker_%s" % self.get_hostname()

    def get_hostname(self):
        return subprocess.check_output(["hostname"]).strip()

    def _stop(self):
        self.logger.info("signing out...")
        if(self._manager):
            self._manager.worker_signout(self.get_hostname())
        self.logger.info("shutting down...")
        self._ns.remove(self._get_pyroname())
        self._ns.remove(self._get_pyroname()+".mnManager")
        self._pyrodaemon.unregister(self)
        self._pyrodaemon.shutdown()
        self._pyrodaemon.close()

    def remoteShutdown(self):
        self._pyrodaemon.shutdown()

    def _check_shutdown(self):
        return self._shutdown

    def stop(self):
        (signedin, assigned) = self._manager.get_worker_status(self.get_hostname())
        if(assigned):
            self.logger.warn("can't shut down as worker is still assigned to id %d" % assigned)
            return False
        else:
            self._stop()
            return True

    def check_output(self, cmd):
        self.logger.debug("Executing %s" % cmd)
        return subprocess.check_output(cmd, shell=True,
                                       stderr=subprocess.STDOUT).strip()

    def script_check_output(self, cmd):
        # Prefix command by our worker directory
        cmd = Tools.get_script_dir() + cmd
        return self.check_output(cmd)

    def run_cmd(self, command):
        subprocess.call(command, shell=True)

    def daemonize(self, cmd):
        p = subprocess.Popen(cmd, shell=True)
        atexit.register(p.terminate)


class MininetManager(object):

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.net = None

    def create_mininet(self, topo, tunnels=[],  switch=UserSwitch,
                       controller=None):
        if(self.net is None):
            self.logger.info("Creating mininet instance")
            if controller:
                self.net = Mininet(topo=topo, intf=TCIntf, link=TCLink,
                                   switch=switch, controller=controller)
            else:
                self.net = Mininet(topo=topo, intf=TCIntf, link=TCLink,
                                   switch=switch)
            self.logger.info("Adding tunnels to mininet instance")
            for tunnel in tunnels:
                port = None
                cls = None
                if "port" in tunnel[2].keys():
                    port = tunnel[2]["port"]
                    del tunnel[2]["port"]
                if "cls" in tunnel[2].keys():
                    cls = tunnel[2]["cls"]
                    del tunnel[2]["cls"]
                self.addTunnel(tunnel[0], tunnel[1], port, cls, **tunnel[2])
            self.logger.info("Starting Mininet...")
            self.net.start()
            self.logger.info("Startup complete.")
            return True
        else:
            self.logger.warn("mininet is already running. can't create new instance.")
            return False

    def destroy_mininet(self):
        if self.net:
            self.net.stop()
            self.logger.info("mininet instance terminated")
            self.net = None

    def configLinkStatus(self, src, dst, status):
        self.net.configLinkStatus(src, dst, status)

    def rpc(self, hostname, cmd, *params1, **params2):
        h = self.net.get(hostname)
        return getattr(h, cmd)(*params1, **params2)

    def attr(self, hostname, name):
        h = self.net.get(hostname)
        return getattr(h, name)

    def addHost(self, name, cls=None, **params):
        self.net.addHost(name, cls, **params)
        return name

    def addSwitch(self, name, cls=None, **params):
        self.net.addSwitch(name, cls, **params)
        #TODO: This should not be done here
        self.net.get(name).start(self.net.controllers)
        return name

    def addController(self, name="c0", controller=None, **params):
        self.net.addController(name, controller, **params)
        return name

    def addTunnel(self, name, switch, port, intf, **params):
        switch = self.net.get(switch)
        if not intf:
            intf = TCIntf
        intf(name, node=switch, port=port, link=None, **params)

    def tunnelX11(self, node, display):
        node = self.net.get(node)
        mininet.term.tunnelX11(node, display)

    def addLink(self, node1, node2, port1=None, port2=None, cls=None,
                **params):
        node1 = self.net.get(node1)
        node2 = self.net.get(node2)
        l = self.net.addLink(node1, node2, port1, port2, cls, **params)
        return ((node1.name, l.intf1.name), (node2.name, l.intf2.name))

    def runCmdOnHost(self, hostname, command, noWait=False):
        '''
            e.g. runCmdOnHost('h1', 'ifconfig')
        '''
        h1 = self.net.get(hostname)
        if noWait:
            return h1.sendCmd(command)
        else:
            return h1.cmd(command)


def main():
    WorkerServer().start(ip=sys.argv[1], port=int(sys.argv[2]), password=sys.argv[3])


if(__name__ == "__main__"):
    main()
