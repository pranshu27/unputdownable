gpt_prompts = {
        "extraction_prompt": """ Role: Tableau Prep Data Analyst - Source and Output Node Extractor

Objective: Analyze a single node from a Tableau Prep ETL file (JSON). The node may represent a **data source** or **output**. Extract only relevant details related to sources and outputs. Do not extract transformation nodes, custom calculation nodes, or intermediary logic.

Instructions:

1. Identify if the node is a **Data Source** or an **Output**. Ignore all other node types (e.g., Join, Union, Aggregate, Filter, Calculation, Annotation).

2. If the node is a **Data Source**, extract and return the following:
   - Node name
   - Node ID
   - Base type
   - Description (if any)
   - Source type (File, Database, Extract, or Manual Input)
   - Connection details (file path, server name, database name, etc.)
   - Authentication method (if available)
   - Field names and data types
   - Number of rows (for manual inputs)
   - Any relevant metadata

3. If the node is an **Output**, extract and return the following:
   - Node name
   - Node ID
   - Base type
   - Description (if any)
   - Destination type (File, Database, Extract, Published Data Source)
   - Output format (e.g., CSV, Hyper, Excel)
   - Connection details (file path, server name, database name, etc.)
   - Field names and data types
   - Any relevant metadata

4. Only include fields and structures relevant to the source or output node. Ignore transformation logic, union/join details, and custom calculations.

5. The output must be a strictly valid JSON object with the following top-level keys:
   - `"source"`: Object containing data source details or null
   - `"output"`: Object containing output details or null

6. If the node is neither a source nor an output, set both "source" and "output" to null.

Output: The final result must be strictly valid JSON and contain no extra commentary or explanation.

Use the above instructions to generate the final JSON output for the provided single node from the Tableau Prep file.
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