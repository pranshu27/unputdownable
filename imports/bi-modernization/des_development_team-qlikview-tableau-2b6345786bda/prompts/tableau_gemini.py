

gemini_prompts = {
        "extraction_prompt": """ Role: Tableau Prep Data Analyst - Source and Output Extractor
Objective: Analyze a single node from a Tableau Prep ETL file (XML/JSON). The node may be an outer container or an inner node representing a data source or output. Extract all relevant details as valid JSON using the provided output schema as reference.

Instructions:
1. Extract the outer node’s key properties: type, name, ID, base type, serialization flag, node description (generate a concise summary if none is provided), and its next node IDs.
2. For inner nodes, extract details based on type:
  - Data Source: Include connection details, source name, field names with types, connection attributes, authentication, and next node IDs, along with a concise node description.
  - Output: Include connection details, base type, field names with types, a concise node description, output type, output details, previous and next node IDs, and the serialization flag.
3. For output nodes, if the node is the source (or first node), assign the outer node's ID as the previous node.
4. General Extraction Guidelines:
  - Traverse the node structure recursively.
  - If a node has a 'loomContainer', extract all nodes within 'loomContainer.nodes'.
  - For nodes contained within a container, if a node's ID matches the 'nodeId' specified in the container's 'namespacesToOutput', assign the container's 'nextNodes' as its 'nextnodeId'; otherwise, retain the node's own 'nextNodes'.
  - Verify that every field defined in the provided JSON schema is present and accurate, including node descriptions, nextnodeIds, and previousnodeIds at both the node and field levels.
5. **EDGE CASE GUIDELINES:
  - Consistently output both nextnodeIds and previousnodeIds for every node, inner and outer. If these are missing in the source data, they must be generated or set to an empty list to maintain schema consistency.
  - For container nodes, ensure that the first inner node's previousnodeId is set to the container node’s ID.
  - Present the final extraction as a single JSON object with the keys: "source", and "output".

Output the final result strictly as valid JSON without any additional natural language text.
            """ ,
        "inner_order_prompt": """
    You are a Data Analyst. Your task is to analyze a Tableau Prep exported JSON file and identify the order of execution of the nodes.

        Instructions:
        1. Determine the Order of Execution - Identify the sequence in which the nodes are executed.
        2. Describe Each Node - Provide a clear explanation of what each node does and how it functions within the workflow.

        Expected output contains :  serial number \t Node ID\t description ( no new lines in the description, it should be in paragraph)
        ** Do not summarize or combine the nodes , all node id must be present in the output.**

        Output must be be seperated by new line for new nodeid and internally for each serial number , node id and description must be tab seperated 
    """,
        "outer_order_prompt":"""
You are a Data Analyst. Your task is to analyze a Tableau Prep exported JSON file and identify the order of execution of the nodes.

    Instructions:
    1. Determine the Order of Execution - Identify the sequence in which the nodes are executed.
    2. Describe Each Node - Provide a clear explanation of what each node does and how it functions within the workflow.

    Expected output contains :  serial number \t Node ID\t description ( no new lines in the description, it should be in paragraph)
    ** Do not summarize or combine the nodes , all node id must be present in the output.**
    ** Do not include next node ids in the output **

    Output must be be seperated by new line for new nodeid and internally for each serial number , node id and description must be tab seperated 
""",

}