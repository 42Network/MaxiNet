install:
	python2 setup.py install
	mkdir -p /usr/local/share/MaxiNet
	cp -rv MaxiNet/Frontend/examples /usr/local/share/MaxiNet/
	cp -rv MaxiNet-cfg-sample /usr/local/share/MaxiNet/config.example

clean:
	-rm -rf build
	-rm -rf dist

uninstall:
	rm -rf /usr/local/lib/python2.7/dist-packages/MaxiNet-*/
	rm -rf /usr/local/share/MaxiNet
	rm /usr/local/bin/MaxiNetServer

reinstall: uninstall clean install

.PHONY: clean install uninstall reinstall
