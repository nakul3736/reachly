-- Runs once, on first initialisation of the data volume.
--
-- The test suite drops every table between tests. Pointing it at the development
-- database would leave alembic_version claiming head with no tables present, and
-- `alembic revision --autogenerate` would then emit a migration recreating tables
-- that already exist in real deployments. A separate database removes the hazard
-- rather than relying on remembering the ordering.
CREATE DATABASE reachly_test OWNER reachly;
