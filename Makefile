build-wheel:
	python setup.py sdist bdist_wheel

clean:
	rm -rf ./build ./dist .tox/ *.egg-info

deploy:
	python -m twine upload dist/*
