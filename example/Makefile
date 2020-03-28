run:
	python run.py

webpack-dev:
	webpack --watch --mode=development

rebuild-parent:
	pip uninstall -y aiodesktop && cd .. && make clean && python setup.py install

rebuild-exe:
	rm -rf ./build ./dist
	pyinstaller run.spec

run-exe:
	./dist/run

rebuild-run: rebuild-parent run
rebuild-exe-run: rebuild-parent rebuild-exe run-exe
