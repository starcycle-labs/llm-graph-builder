import os
from dotenv import load_dotenv
import logging
from neo4j import GraphDatabase
from datetime import datetime


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load environment variables
load_dotenv()

def create_graph_database_connection(uri, userName, password, database):
    """Create a connection to the Neo4j database"""
    try:
        graph = GraphDatabase.driver(uri, auth=(userName, password))
        logging.info(f"Successfully connected to Neo4j database: {database}")
        return graph
    except Exception as e:
        logging.error(f"Failed to connect to Neo4j database: {str(e)}")
        raise

def inspect_document_nodes(graph):
    """Inspect the properties of Document nodes"""
    try:
        query = """
        MATCH (d:Document)
        RETURN d
        LIMIT 1
        """
        with graph.session(database="adrubix") as session:
            result = session.run(query)
            record = result.single()
            if record:
                node = record["d"]
                properties = dict(node)
                logging.info("Document node properties:")
                for key, value in properties.items():
                    logging.info(f"  {key}: {value}")
                return list(properties.keys())
            return []
    except Exception as e:
        logging.error(f"Failed to inspect document nodes: {str(e)}")
        raise

def get_all_source_nodes(graph):
    """Get all source nodes from the database"""
    try:
        # First inspect what properties exist
        properties = inspect_document_nodes(graph)
        if not properties:
            logging.error("No Document nodes found or no properties available")
            return []

        # Use the actual property names we found
        query = """
        MATCH (d:Document)
        RETURN d
        """
        with graph.session(database="adrubix") as session:
            result = session.run(query)
            nodes = []
            for record in result:
                node = record["d"]
                properties = dict(node)
                nodes.append(properties)
            logging.info(f"Found {len(nodes)} source nodes in database")
            return nodes
    except Exception as e:
        logging.error(f"Failed to get source nodes: {str(e)}")
        raise

def delete_source_node_and_related_data(graph, node):
    """Delete a source node and all its related data"""
    try:
        # Get the actual file name from the node properties
        file_name = node.get("name") or node.get("fileName") or node.get("file_name")
        if not file_name:
            logging.error(f"Could not find file name in node properties: {node}")
            return False

        # Delete relationships and nodes in this order to avoid constraint violations
        queries = [
            # Delete relationships between chunks and entities
            """
            MATCH (c:Chunk)-[r:HAS_ENTITY]->(e:Entity)
            WHERE c.fileName = $file_name OR c.name = $file_name
            DELETE r
            """,
            # Delete relationships between chunks
            """
            MATCH (c1:Chunk)-[r:NEXT_CHUNK]->(c2:Chunk)
            WHERE c1.fileName = $file_name OR c1.name = $file_name
            DELETE r
            """,
            # Delete relationships between entities
            """
            MATCH (e1:Entity)-[r]-(e2:Entity)
            WHERE e1.fileName = $file_name OR e1.name = $file_name
            DELETE r
            """,
            # Delete chunk nodes
            """
            MATCH (c:Chunk)
            WHERE c.fileName = $file_name OR c.name = $file_name
            DELETE c
            """,
            # Delete entity nodes
            """
            MATCH (e:Entity)
            WHERE e.fileName = $file_name OR e.name = $file_name
            DELETE e
            """,
            # Finally delete the document node
            """
            MATCH (d:Document)
            WHERE d.name = $file_name OR d.fileName = $file_name
            DELETE d
            """
        ]
        
        with graph.session(database="adrubix") as session:
            for query in queries:
                try:
                    result = session.run(query, file_name=file_name)
                    logging.info(f"Executed query for file {file_name}: {query[:50]}...")
                except Exception as e:
                    logging.error(f"Error executing query: {str(e)}")
                    raise
                    
        logging.info(f"Successfully deleted all data for file: {file_name}")
        return True
    except Exception as e:
        logging.error(f"Failed to delete data for file {file_name}: {str(e)}")
        return False

def main():
    """Main function to clean up the database"""
    try:
        # Get database connection details from environment variables
        uri = os.getenv("NEO4J_URI")
        userName = os.getenv("NEO4J_USERNAME")
        password = os.getenv("NEO4J_PASSWORD")
        database = "adrubix"  # Explicitly set to use the test database

        if not all([uri, userName, password]):
            raise ValueError("Missing required environment variables")

        # Create database connection
        graph = create_graph_database_connection(uri, userName, password, database)
        
        # Get all source nodes
        source_nodes = get_all_source_nodes(graph)
        
        # Track deletion results
        success_count = 0
        failure_count = 0
        failed_files = []
        
        # Delete each source node and its related data
        for node in source_nodes:
            file_name = node.get("name") or node.get("fileName") or node.get("file_name")
            status = node.get("status")
            file_source = node.get("file_source") or node.get("source")
            
            logging.info(f"\nProcessing deletion for node:")
            logging.info(f"  Properties: {node}")
            logging.info(f"  File name: {file_name}")
            logging.info(f"  Status: {status}")
            logging.info(f"  Source: {file_source}")
            
            if delete_source_node_and_related_data(graph, node):
                success_count += 1
            else:
                failure_count += 1
                failed_files.append(file_name or "Unknown")
        
        # Log summary
        logging.info("\n=== Deletion Summary ===")
        logging.info(f"Total files processed: {len(source_nodes)}")
        logging.info(f"Successfully deleted: {success_count}")
        logging.info(f"Failed to delete: {failure_count}")
        
        if failed_files:
            logging.info("\nFailed files:")
            for file_name in failed_files:
                logging.info(f"- {file_name}")
        
    except Exception as e:
        logging.error(f"Script failed: {str(e)}")
        raise
    finally:
        if 'graph' in locals():
            graph.close()

if __name__ == "__main__":
    main() 