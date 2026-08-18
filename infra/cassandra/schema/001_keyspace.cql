CREATE KEYSPACE IF NOT EXISTS iot
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
-- Local dev only (single Cassandra node). Production (REQUIREMENTS.md §4.1, delivered in
-- P6) uses NetworkTopologyStrategy with replication_factor 2 across the two Contabo data
-- nodes. Out of scope for P1.
