.PHONY: test

test:
	PYTHONPATH=src python -m unittest discover -s tests -v

integration:
	@test -n "$$CONTINUUM_DATABASE_URL" || \
		(echo "CONTINUUM_DATABASE_URL is required" && exit 1)
	PYTHONPATH=src python -m unittest tests.test_cockroach_integration -v
