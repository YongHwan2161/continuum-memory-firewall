.PHONY: test integration mcp-test cloud-package

test:
	PYTHONPATH=src python -m unittest discover -s tests -v

integration:
	@test -n "$$CONTINUUM_DATABASE_URL" || \
		(echo "CONTINUUM_DATABASE_URL is required" && exit 1)
	PYTHONPATH=src python -m unittest tests.test_cockroach_integration -v

mcp-test:
	PYTHONPATH=src python -m unittest tests.test_mcp_server -v

cloud-package:
	./scripts/build_lambda_package.sh
	unzip -t build/aws/continuum-managed-mcp-worker.zip
