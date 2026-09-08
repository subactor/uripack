.PHONY: test test-docker test-all demo build validate

test:
	python -m pytest -q

test-docker:
	python -m pytest -q integration_tests

test-all:
	python -m pytest -q tests integration_tests

demo:
	uripack demo

validate:
	uripack validate-request examples/subactor-extract.yaml
	uripack validate-request examples/subactor-typescript-package.yaml
	python -m pytest -q

build:
	python -c 'from setuptools.build_meta import build_wheel, build_sdist; build_wheel("dist"); build_sdist("dist")'
