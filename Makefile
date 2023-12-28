.PHONY: test
test:
	PYTHONPATH=src python -m unittest

.PHONY: clean
clean:
	rm -rf dist

dist: test
	python -m build --sdist .

.PHONY: deploy_test
deploy_test: dist
	twine check dist/*
	# https://test.pypi.org/project/gcode-machine
	# python3 -m pip install --index-url https://test.pypi.org/simple/ gcode-machine
	twine upload --repository testpypi --sign dist/*

.PHONY: deploy_PRODUCTION
deploy_PRODUCTION: dist
	twine check dist/*
	# https://pypi.org/project/gcode-machine
	# python3 -m pip install gcode-machine
	twine upload --sign dist/*
