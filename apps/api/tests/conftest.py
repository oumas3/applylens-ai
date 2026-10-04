"""Keep unit tests isolated from developer and production environment files."""

import os


test_database_url = os.getenv("TEST_DATABASE_URL")
os.environ["DATABASE_URL"] = test_database_url or " "
os.environ["DOCUMENT_STORAGE"] = "local"
os.environ["RETRIEVAL_PROVIDER"] = "lexical"
os.environ["RETRIEVAL_STORAGE"] = "memory"
