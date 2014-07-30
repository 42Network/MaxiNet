#!/usr/bin/python2

#
# Minimal example showing how to use MaxiNet with OpenFlow 1.3.
# Make sure your controller is able to handle OpenFlow 1.3.
#

import sys
sys.path.append("..")
import maxinet
import time
from mininet.node import OVSSwitch
from fatTree import FatTree

topo = FatTree(4,10,0.1)
cluster = maxinet.Cluster()
cluster.start()

exp = maxinet.Experiment(cluster, topo,switch=OVSSwitch)
exp.setup()

#Enable OpenFlow 1.3 on all switches
for switch in exp.switches:
    exp.get_worker(switch).run_cmd('ovs-vsctl -- set Bridge %s protocols=OpenFlow10,OpenFlow12,OpenFlow13' % switch.name) 

#Create some Flows
print exp.get_node("h1").cmd("ping -c 5 10.0.0.4")

#Dump Flows with OpenFlow 1.3 Command
print exp.get("s1").dpctl("-O OpenFlow13 dump-flows")

exp.stop()
