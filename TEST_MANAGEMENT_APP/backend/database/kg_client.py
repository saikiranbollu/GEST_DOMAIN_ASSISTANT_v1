"""
KG (Knowledge Graph) Client
Queries Neo4j knowledge graph for dependencies, relationships, and traceability
Supports unlimited modules dynamically (CXPI, LIN, BTL, SWA, etc.)
"""

import logging
from typing import List, Dict, Any, Optional, Set
from neo4j import GraphDatabase, Session, NotificationDisabledClassification
from neo4j.exceptions import Neo4jError
from dotenv import load_dotenv
import os
import warnings

logger = logging.getLogger(__name__)

# Suppress noisy Neo4j driver notifications (GqlStatusObject warnings about
# non-existent labels/properties/relationships that are just informational)
logging.getLogger("neo4j").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=DeprecationWarning, module="neo4j")

# Load environment variables
load_dotenv()


class KGClient:
    """
    Neo4j Knowledge Graph client for querying relationships and dependencies
    
    """
    
    def __init__(self, uri: Optional[str] = None, user: Optional[str] = None, password: Optional[str] = None, module: Optional[str] = None, database: Optional[str] = None):
        """
        Initialize Knowledge Graph client
        
        Args:
            uri: Neo4j URI (default: from env NEO4J_URI)
            user: Neo4j username (default: from env NEO4J_USER)
            password: Neo4j password (default: from env NEO4J_PASSWORD)
            module: Module name (e.g., "cxpi", "lin", "btl") - used to derive database name if database not provided
            database: Explicit database name (format: {module}db, e.g., "cxpidb")
                     If not provided, must provide module parameter to derive it dynamically
        
        DYNAMIC & SCALABLE: Zero hardcoding of module names or database names
        Either: 
          - KGClient(module="cxpi") → derives database="cxpidb"
          - KGClient(database="cxpidb") → uses explicit database
          - Set NEO4J_DATABASE env var for database name
          - Set MODULE_NAME env var for module name (database derived as {MODULE_NAME}db)
        """
        # Get Neo4j credentials from environment
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.getenv("NEO4J_USER", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        
        # Determine database name dynamically
        if database:
            # Explicit database provided
            self.database = database
        elif module:
            # Module name provided - derive database name: {module_lowercase}db
            self.database = f"{module.lower()}db"
            self.module_name = module.lower()
        else:
            # Try to get from environment
            self.database = os.getenv("NEO4J_DATABASE")
            module_env = os.getenv("MODULE_NAME")
            
            if not self.database and module_env:
                # MODULE_NAME env var provided - derive database
                self.database = f"{module_env.lower()}db"
                self.module_name = module_env.lower()
            elif not self.database:
                # No database name available - error
                raise ValueError(
                    "Must provide database name via one of:\n"
                    "  1. database parameter: KGClient(database='cxpidb')\n"
                    "  2. module parameter: KGClient(module='cxpi')\n"
                    "  3. NEO4J_DATABASE env var\n"
                    "  4. MODULE_NAME env var (derives database as {MODULE_NAME}db)\n"
                    "Database format must be: {module_name_lowercase}db (e.g., cxpidb, lindb, btmdb)"
                )
            else:
                self.module_name = self.database.replace("db", "").lower()
        
        try:
            self.driver = GraphDatabase.driver(
                self.uri, 
                auth=(self.user, self.password),
                notifications_disabled_classifications=[
                    NotificationDisabledClassification.UNRECOGNIZED,
                    NotificationDisabledClassification.HINT,
                    NotificationDisabledClassification.PERFORMANCE,
                    NotificationDisabledClassification.GENERIC,
                    NotificationDisabledClassification.SCHEMA,
                ]
            )
            # Verify connection with specified database
            with self.driver.session(database=self.database) as session:
                result = session.run("RETURN 1")
                result.consume()
            logger.info(f"[KG] Connected to Neo4j at {self.uri} (database: {self.database})")
        except Neo4jError as e:
            logger.error(f"[KG-ERROR] Failed to connect to Neo4j database '{self.database}': {e}")
            raise
    
    def close(self):
        """Close Neo4j connection"""
        if self.driver:
            self.driver.close()
    
    def get_function_dependencies(self, func_name: str) -> List[Dict[str, Any]]:
        """
        Get all functions that a function depends on
        
        Args:
            func_name: Function name to search for
            
        Returns:
            List of dependent functions with relationship type
        """
        query = """
            MATCH (f:Function {name: $func_name})-[rel:DEPENDS_ON|CALLS_INTERNALLY]->(dep:Function)
            RETURN dep.name as dependency, 
                   type(rel) as relationship, 
                   dep.return_type as return_type
            ORDER BY dep.name
        """
        
        return self._run_query(query, {"func_name": func_name})
    
    def get_function_calls(self, func_name: str) -> List[Dict[str, Any]]:
        """
        Get all functions called by a specific function
        
        Args:
            func_name: Function name
            
        Returns:
            List of functions that are called
        """
        query = """
            MATCH (f:Function {name: $func_name})-[:CALLS_INTERNALLY]->(called:Function)
            RETURN called.name as function_called,
                   called.return_type as return_type
            ORDER BY called.name
        """
        
        return self._run_query(query, {"func_name": func_name})
    
    def get_function_parameters(self, func_name: str) -> List[Dict[str, Any]]:
        """
        Get parameters of a function with their types
        
        Args:
            func_name: Function name
            
        Returns:
            List of parameters with types and metadata
        """
        query = """
            MATCH (f:Function {name: $func_name})-[:HAS_PARAMETER]->(param:Parameter)
            OPTIONAL MATCH (param)-[:OF_TYPE]->(type_node)
            RETURN param.name as param_name,
                   param.type as param_type_direct,
                   type_node.name as param_type,
                   param.description as description,
                   param.param_index as param_index
            ORDER BY param.param_index
        """
        
        return self._run_query(query, {"func_name": func_name})
    
    def get_type_definition(self, type_name: str) -> Dict[str, Any]:
        """
        Get struct/enum type definition with all fields
        
        Args:
            type_name: Type name (struct or enum)
            
        Returns:
            Type definition with fields/values and metadata
        """
        # Check for struct
        query_struct = """
            MATCH (s:Struct {name: $type_name})
            OPTIONAL MATCH (s)-[:HAS_MEMBER]->(member:StructMember)
            RETURN s.name as name,
                   "Struct" as type,
                   s.description as description,
                   collect({
                       name: member.name,
                       type: member.type,
                       bit_offset: member.bit_offset,
                       bit_length: member.bit_length
                   }) as fields
        """
        
        # Check for enum
        query_enum = """
            MATCH (e:Enum {name: $type_name})
            OPTIONAL MATCH (e)-[:HAS_VALUE]->(value:EnumValue)
            RETURN e.name as name,
                   "Enum" as type,
                   e.description as description,
                   collect({
                       name: value.name,
                       value: value.value,
                       description: value.description
                   }) as fields
        """
        
        # Try struct first
        result = self._run_query(query_struct, {"type_name": type_name})
        if result:
            return result[0] if result else {}
        
        # Try enum
        result = self._run_query(query_enum, {"type_name": type_name})
        return result[0] if result else {}
    
    def get_requirement_traceability(self, req_id: str) -> Dict[str, Any]:
        """
        Get traceability chain: requirement -> implementation -> tests
        
        Args:
            req_id: Requirement ID or name
            
        Returns:
            Traceability information with all related items
        """
        query = """
            MATCH (req:Requirement {id: $req_id})
            OPTIONAL MATCH (req)<-[:IMPLEMENTS]-(func:Function)
            RETURN req.id as requirement_id,
                   req.description as requirement_desc,
                   collect(distinct {
                       function: func.name,
                       return_type: func.return_type,
                       brief: func.brief
                   }) as implementations
        """
        
        result = self._run_query(query, {"req_id": req_id})
        return result[0] if result else {}
    
    def find_functions_by_pattern(self, pattern: str) -> List[Dict[str, Any]]:
        """
        Find functions matching a pattern (name, parameters, return type)
        
        Args:
            pattern: Search pattern (supports regex-like matching)
            
        Returns:
            List of matching functions
        """
        query = """
            MATCH (f:Function)
            WHERE f.name CONTAINS $pattern 
               OR f.description CONTAINS $pattern
               OR f.return_type CONTAINS $pattern
            RETURN f.name as name,
                   f.return_type as return_type,
                   f.description as description,
                   f.brief as brief
            ORDER BY f.name
            LIMIT 20
        """
        
        return self._run_query(query, {"pattern": pattern})
    
    def get_affected_items(self, item_name: str) -> Dict[str, List]:
        """
        Get all items affected by a change to a specific item
        
        Args:
            item_name: Item name (function, type, module)
            
        Returns:
            Dictionary of affected items by type
        """
        query = """
            MATCH (item {name: $item_name})
            OPTIONAL MATCH (item)-[:DEPENDS_ON|CALLS_INTERNALLY]->(directly_dep:Function)
            OPTIONAL MATCH (item)-[:CALLS_INTERNALLY*1..3]->(downstream:Function)
            OPTIONAL MATCH (item)<-[:DEPENDS_ON|CALLS_INTERNALLY]-(upstream:Function)
            RETURN collect(distinct directly_dep.name) as directly_affected,
                   collect(distinct downstream.name) as downstream_impact,
                   collect(distinct upstream.name) as upstream_dependent
        """
        
        result = self._run_query(query, {"item_name": item_name})
        if result:
            r = result[0]
            return {
                'directly_affected': r['directly_affected'] or [],
                'downstream_impact': r['downstream_impact'] or [],
                'upstream_dependent': r['upstream_dependent'] or []
            }
        return {'directly_affected': [], 'downstream_impact': [], 'upstream_dependent': []}
    
    def get_module_structure(self, module_name: str) -> Dict[str, Any]:
        """
        Get functions, structs, and enums related to a module prefix
        
        Note: No Module node exists in the KG. This queries by name pattern (e.g., 'IfxCxpi' prefix).
        
        Args:
            module_name: Module name prefix to search by (e.g., 'IfxCxpi')
            
        Returns:
            Module structure with all contained items found by name pattern
        """
        # Use name pattern matching since no Module node exists
        pattern = f"(?i).*{module_name}.*"
        query = """
            OPTIONAL MATCH (func:Function) WHERE func.name =~ $pattern
            OPTIONAL MATCH (struct:Struct) WHERE struct.name =~ $pattern
            OPTIONAL MATCH (enum:Enum) WHERE enum.name =~ $pattern
            RETURN collect(distinct func.name) as functions,
                   collect(distinct struct.name) as structs,
                   collect(distinct enum.name) as enums
        """
        
        result = self._run_query(query, {"pattern": pattern})
        if result:
            r = result[0]
            return {
                'module_name': module_name,
                'functions': r.get('functions', []),
                'structs': r.get('structs', []),
                'enums': r.get('enums', [])
            }
        return {'module_name': module_name, 'functions': [], 'structs': [], 'enums': []}
    
    # ================================================================
    # COMPREHENSIVE KG QUERY METHODS (All 22 Relationships)
    # ================================================================
    
    def get_struct_members(self, struct_name: str) -> List[Dict[str, Any]]:
        """
        Get all members of a struct (HAS_MEMBER relationship)
        
        Args:
            struct_name: Struct name
            
        Returns:
            List of struct members with types and descriptions
        """
        query = """
            MATCH (s:Struct {name: $struct_name})-[:HAS_MEMBER]->(member:StructMember)
            OPTIONAL MATCH (member)-[:OF_TYPE]->(type_node)
            RETURN member.name as member_name,
                   type_node.name as member_type,
                   member.description as description,
                   member.offset as offset
            ORDER BY member.name
        """
        return self._run_query(query, {"struct_name": struct_name})
    
    def get_enum_values(self, enum_name: str) -> List[Dict[str, Any]]:
        """
        Get all values of an enum (HAS_VALUE relationship)
        
        Args:
            enum_name: Enum name
            
        Returns:
            List of enum values with numeric values and descriptions
        """
        query = """
            MATCH (e:Enum {name: $enum_name})-[:HAS_VALUE]->(val:EnumValue)
            OPTIONAL MATCH (val)-[:INDICATES]->(condition:Condition)
            RETURN val.name as value_name,
                   val.value as numeric_value,
                   val.description as description,
                   condition.name as indicates_condition
            ORDER BY val.value
        """
        return self._run_query(query, {"enum_name": enum_name})
    
    def get_requirements_by_function(self, func_name: str) -> List[Dict[str, Any]]:
        """
        Get requirements implemented by a function (IMPLEMENTS relationship)
        
        Args:
            func_name: Function name
            
        Returns:
            List of requirements this function implements
        """
        query = """
            MATCH (f:Function {name: $func_name})-[:IMPLEMENTS]->(req:Requirement)
            RETURN req.id as requirement_id,
                   req.name as requirement_name,
                   req.description as requirement_description
            ORDER BY req.id
        """
        return self._run_query(query, {"func_name": func_name})
    
    def get_functions_by_requirement(self, requirement_id: str) -> List[Dict[str, Any]]:
        """
        Get functions that implement a requirement (IMPLEMENTED_BY relationship)
        
        Args:
            requirement_id: Requirement ID (e.g., "REQ_5")
            
        Returns:
            List of functions implementing this requirement
        """
        query = """
            MATCH (req:Requirement {id: $requirement_id})-[:IMPLEMENTED_BY]->(func:Function)
            RETURN func.name as function_name,
                   func.return_type as return_type,
                   func.brief as description
            ORDER BY func.name
        """
        return self._run_query(query, {"requirement_id": requirement_id})
    
    def get_register_bitfields(self, register_name: str) -> List[Dict[str, Any]]:
        """
        Get all bitfields of a register (HAS_BITFIELD relationship)
        
        Args:
            register_name: Register name
            
        Returns:
            List of bitfields with bit ranges and access types
        """
        query = """
            MATCH (r:Register {name: $register_name})-[:HAS_BITFIELD]->(bf:BitField)
            OPTIONAL MATCH (bf)-[:CONTROLS]->(op:Operation)
            RETURN bf.name as bitfield_name,
                   bf.width as bit_width,
                   bf.bit_range as bit_range,
                   bf.description as description,
                   bf.access as access_type,
                   op.name as controls_operation
            ORDER BY bf.bit_range
        """
        return self._run_query(query, {"register_name": register_name})
    
    def get_controlled_operations(self, bitfield_name: str) -> List[Dict[str, Any]]:
        """
        Get operations controlled by a bitfield (CONTROLS relationship)
        
        Args:
            bitfield_name: Bitfield name
            
        Returns:
            List of hardware operations this bitfield controls
        """
        query = """
            MATCH (bf:BitField {name: $bitfield_name})-[:CONTROLS]->(op:Operation)
            RETURN op.name as operation_name,
                   op.description as operation_description,
                   op.type as operation_type
            ORDER BY op.name
        """
        return self._run_query(query, {"bitfield_name": bitfield_name})
    
    def get_hardware_register_fields(self, register_name: str) -> List[Dict[str, Any]]:
        """
        Get hardware register fields (HAS_FIELD relationship)
        
        Args:
            register_name: Hardware register name
            
        Returns:
            List of register fields with access types
        """
        query = """
            MATCH (hr:HardwareRegister {name: $register_name})-[:HAS_FIELD]->(field:RegisterField)
            OPTIONAL MATCH (field)-[:ACCESS_TYPE]->(access:AccessMode)
            RETURN field.name as field_name,
                   field.bits as bit_position,
                   field.description as description,
                   field.type as field_access_type,
                   access.name as access_mode
            ORDER BY field.bits
        """
        return self._run_query(query, {"register_name": register_name})
    
    def get_register_memory_location(self, register_name: str) -> Dict[str, Any]:
        """
        Get memory address of a register (LOCATED_AT relationship)
        
        Args:
            register_name: Register name
            
        Returns:
            Memory location info (address, offset)
        """
        query = """
            MATCH (r:HardwareRegister {name: $register_name})-[:LOCATED_AT]->(mem:MemoryLocation)
            RETURN r.name as register_name,
                   r.offset as offset,
                   mem.address as memory_address,
                   r.reset_value as reset_value
        """
        result = self._run_query(query, {"register_name": register_name})
        return result[0] if result else {}
    
    def get_interrupt_triggers(self, operation_name: str) -> List[Dict[str, Any]]:
        """
        Get interrupts triggered by an operation (TRIGGERED_BY relationship)
        
        Args:
            operation_name: Operation name
            
        Returns:
            List of interrupts triggered by this operation
        """
        query = """
            MATCH (op:Operation {name: $operation_name})<-[:TRIGGERED_BY]-(intr:Interrupt)
            RETURN intr.name as interrupt_name,
                   intr.description as interrupt_description,
                   intr.bit_position as bit_position,
                   intr.register as register_name
            ORDER BY intr.name
        """
        return self._run_query(query, {"operation_name": operation_name})
    
    def get_error_detection_registers(self, error_name: str) -> List[Dict[str, Any]]:
        """
        Get registers that detect an error (DETECTED_BY relationship)
        
        Args:
            error_name: Error name
            
        Returns:
            List of registers that report this error
        """
        query = """
            MATCH (err:Error {name: $error_name})-[:DETECTED_BY]->(reg:Register)
            RETURN err.name as error_name,
                   err.description as error_description,
                   err.severity as severity,
                   reg.name as detecting_register,
                   err.register_bit as bit_position
            ORDER BY reg.name
        """
        return self._run_query(query, {"error_name": error_name})
    
    def get_switch_cases(self, function_name: str) -> List[Dict[str, Any]]:
        """
        Get switch case variants of a dispatcher function (HAS_CASE relationship)
        
        Args:
            function_name: Dispatcher function name
            
        Returns:
            List of case variants with their internal calls
        """
        query = """
            MATCH (f:Function {name: $function_name})-[:HAS_CASE]->(c:EnumValue)
            OPTIONAL MATCH (c)-[:CALLS_INTERNALLY]->(internal:Function)
            RETURN c.name as case_variant,
                   c.value as case_value,
                   collect(internal.name) as internal_calls
            ORDER BY c.value
        """
        return self._run_query(query, {"function_name": function_name})
    
    def get_enum_semantic_meaning(self, enum_value_name: str) -> Dict[str, Any]:
        """
        Get semantic meaning of an enum value (INDICATES relationship)
        
        Args:
            enum_value_name: Enum value name (e.g., "IfxCxpi_Status_success")
            
        Returns:
            Condition/state this enum value indicates
        """
        query = """
            MATCH (val:EnumValue {name: $enum_value_name})-[:INDICATES]->(cond:Condition)
            RETURN val.name as enum_value,
                   val.value as numeric_value,
                   cond.name as indicates_condition,
                   cond.description as condition_description
        """
        result = self._run_query(query, {"enum_value_name": enum_value_name})
        return result[0] if result else {}
    
    def get_type_users(self, type_name: str) -> List[Dict[str, Any]]:
        """
        Get functions that use a specific struct/typedef (USED_BY relationship)
        
        Args:
            type_name: Struct or typedef name
            
        Returns:
            List of functions using this type
        """
        query = """
            MATCH (type {name: $type_name})-[:USED_BY]->(func:Function)
            RETURN func.name as function_name,
                   func.return_type as return_type,
                   func.brief as description
            ORDER BY func.name
        """
        return self._run_query(query, {"type_name": type_name})
    
    def get_typedef_primitive_mapping(self, typedef_name: str) -> Dict[str, Any]:
        """
        Get primitive type that a typedef aliases (ALIASES relationship)
        
        Args:
            typedef_name: Typedef name
            
        Returns:
            Primitive type info
        """
        query = """
            MATCH (td:Typedef {name: $typedef_name})-[:ALIASES]->(prim:PrimitiveType)
            RETURN td.name as typedef_name,
                   prim.name as primitive_type,
                   td.brief as description
        """
        result = self._run_query(query, {"typedef_name": typedef_name})
        return result[0] if result else {}
    
    def get_typedef_usage_in_structs(self, typedef_name: str) -> List[Dict[str, Any]]:
        """
        Get structs that use a typedef (USED_IN relationship)
        
        Args:
            typedef_name: Typedef name
            
        Returns:
            List of structs using this typedef
        """
        query = """
            MATCH (td:Typedef {name: $typedef_name})-[:USED_IN]->(struct:Struct)
            RETURN struct.name as struct_name,
                   struct.brief as description
            ORDER BY struct.name
        """
        return self._run_query(query, {"typedef_name": typedef_name})
    
    def find_circular_dependencies(self) -> List[List[str]]:
        """
        Find all circular dependencies in the knowledge graph
        
        Returns:
            List of dependency cycles (each cycle is a list of item names)
        """
        query = """
            MATCH p=(n)-[r:DEPENDS_ON|CALLS_INTERNALLY*2..]->(n)
            WHERE none(x in nodes(p)[0..-1] WHERE x = n)
            WITH nodes(p) as cycle
            RETURN [node in cycle | node.name] as dependency_cycle
        """
        
        return self._run_query(query, {})
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get overall statistics about the knowledge graph
        
        Returns:
            Statistics about nodes and relationships
        """
        query = """
            MATCH (n)
            WITH labels(n) as label, count(*) as count
            WITH collect({label: label[0], count: count}) as node_counts
            
            MATCH ()-[r]->()
            WITH node_counts, type(r) as rel_type, count(*) as rel_count
            WITH node_counts, collect({type: rel_type, count: rel_count}) as rel_counts
            
            RETURN {
                node_types: node_counts,
                relationship_types: rel_counts,
                total_nodes: reduce(s = 0, nc in node_counts | s + nc.count),
                total_relationships: reduce(s = 0, rc in rel_counts | s + rc.count)
            } as statistics
        """
        
        result = self._run_query(query, {})
        return result[0] if result else {}
    
    def query(self, cypher: str, parameters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Public query method - runs a raw Cypher query
        
        Args:
            cypher: Cypher query string
            parameters: Optional query parameters
            
        Returns:
            List of result records as dictionaries
        """
        return self._run_query(cypher, parameters or {})
    
    def _run_query(self, query: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Run a Cypher query and return results
        
        Args:
            query: Cypher query string
            parameters: Query parameters
            
        Returns:
            List of result records as dictionaries
        """
        try:
            with self.driver.session(database=self.database) as session:
                result = session.run(query, parameters)
                return [dict(record) for record in result]
        except Neo4jError as e:
            logger.error(f"[KG-ERROR] Query failed: {e}\nQuery: {query}")
            return []
        except Exception as e:
            logger.error(f"[KG-ERROR] Unexpected error: {e}")
            return []


# Test/Demo code
if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # Initialize logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("\n" + "="*60)
    print("KG CLIENT TEST")
    print("="*60)
    
    try:
        # Initialize KGClient
        kg = KGClient()
        
        # Test 1: Get statistics
        print("\n📊 Test 1: Knowledge Graph Statistics")
        print("-" * 60)
        stats = kg.get_statistics()
        if stats:
            print(f"KG Statistics: {stats}")
        else:
            print("No statistics available (Neo4j might be empty)")
        
        # Test 2: Find functions
        print("\n🔍 Test 2: Find Functions")
        print("-" * 60)
        funcs = kg.find_functions_by_pattern("init")
        print(f"Found {len(funcs)} functions matching 'init'")
        for func in funcs[:3]:
            print(f"  - {func.get('name', 'N/A')}: {func.get('return_type', 'N/A')}")
        
        # Test 3: Get function calls
        print("\n🔗 Test 3: Function Calls")
        print("-" * 60)
        if funcs:
            first_func = funcs[0]['name']
            calls = kg.get_function_calls(first_func)
            print(f"Function '{first_func}' calls {len(calls)} functions")
            for call in calls[:3]:
                print(f"  - {call.get('function_called', 'N/A')}")
        
        # Test 4: Get function parameters
        print("\n📝 Test 4: Function Parameters")
        print("-" * 60)
        if funcs:
            first_func = funcs[0]['name']
            params = kg.get_function_parameters(first_func)
            print(f"Function '{first_func}' has {len(params)} parameters")
            for param in params[:3]:
                print(f"  - {param.get('param_name', 'N/A')}: {param.get('param_type', 'N/A')}")
        
        # Test 5: Circular dependencies
        print("\n⚠️  Test 5: Circular Dependencies")
        print("-" * 60)
        cycles = kg.find_circular_dependencies()
        if cycles:
            print(f"Found {len(cycles)} circular dependencies")
            for cycle in cycles[:3]:
                print(f"  - {' -> '.join(cycle)}")
        else:
            print("No circular dependencies found")
        
        kg.close()
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("\n" + "="*60)
    print("✓ Test completed")
    print("="*60)
