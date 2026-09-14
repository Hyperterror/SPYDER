from neo4j import GraphDatabase
from app.core.config import settings
from functools import lru_cache


class Neo4jDriver:
    def __init__(self):
        self._driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )

    def close(self):
        self._driver.close()

    def session(self, **kwargs):
        return self._driver.session(**kwargs)

    def verify_connectivity(self):
        self._driver.verify_connectivity()

    def run_query(self, query: str, parameters: dict = None):
        with self._driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def setup_constraints(self):
        """Create Neo4j constraints and indexes for Phase 1 graph model."""
        constraints = [
            """CREATE CONSTRAINT phone_case_number_unique IF NOT EXISTS
               FOR (p:Phone) REQUIRE (p.case_id, p.normalized_number) IS UNIQUE""",
            """CREATE CONSTRAINT account_case_id_unique IF NOT EXISTS
               FOR (a:Account) REQUIRE (a.case_id, a.normalized_identifier) IS UNIQUE""",
            """CREATE CONSTRAINT document_id_unique IF NOT EXISTS
               FOR (d:Document) REQUIRE d.id IS UNIQUE""",
            """CREATE CONSTRAINT device_case_imei_unique IF NOT EXISTS
               FOR (d:Device) REQUIRE (d.case_id, d.imei) IS UNIQUE""",
            """CREATE CONSTRAINT tower_case_id_unique IF NOT EXISTS
               FOR (t:Tower) REQUIRE (t.case_id, t.tower_id) IS UNIQUE""",
            """CREATE INDEX phone_search IF NOT EXISTS
               FOR (p:Phone) ON (p.case_id, p.normalized_number)""",
            """CREATE INDEX account_search IF NOT EXISTS
               FOR (a:Account) ON (a.case_id, a.normalized_identifier)""",
        ]
        for q in constraints:
            try:
                self.run_query(q)
            except Exception:
                pass  # Constraint may already exist


_driver_instance: Neo4jDriver | None = None


def get_neo4j() -> Neo4jDriver:
    global _driver_instance
    if _driver_instance is None:
        _driver_instance = Neo4jDriver()
    return _driver_instance


def close_neo4j():
    global _driver_instance
    if _driver_instance:
        _driver_instance.close()
        _driver_instance = None
