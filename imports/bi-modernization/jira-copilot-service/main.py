import os
import json
import autogen
import requests
import markdown
import pandas as pd
from docx import Document
from atlassian import Jira
from bs4 import BeautifulSoup
from pydantic import BaseModel
from autogen import register_function
from requests.auth import HTTPBasicAuth
from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from AWSSecretsManager import SecretsManagerClient

secrets_manager_client_key = SecretsManagerClient(
    AWS_PROFILE_NAME="409344278376_LLM_Developer",
    AWS_SECRET_NAME="/LLM/Citi/copilot-jira/Application/ApplicationAccessKeys/Azure/dataeconomyllm2/AccessCredentials",
    AWS_REGION_NAME="us-east-2"
)
secrets_manager_client_key.load_secrets_to_env()

config_list = [{
    "model": os.getenv("AZURE_DEPLOYMENT_NAME"),
    "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
    "base_url": os.getenv("AZURE_OPENAI_API_BASE"),
    "api_type": os.getenv("API_TYPE"),
    "api_version": os.getenv("AZURE_OPENAI_API_VERSION")
}]

llm_config = {"cache_seed": None,"config_list": config_list,"temperature":0}

app = FastAPI()

origins = [
    "http://localhost.tiangolo.com",
    "https://localhost.tiangolo.com",
    "http://localhost",
    "http://localhost:8080",
    "*",
    "http://mca-243900498.us-east-2.elb.amazonaws.com",
    "http://copilot-882210223.us-east-2.elb.amazonaws.com"
]
 
class Inputprompt(BaseModel):
    prompt: str
    board_id : str

class InputData(BaseModel):
    Technical_analysis: str
    Executive_summary: str
    response_input: dict
    jira_story_id: str
    file_name: str

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAVE_FOLDER = 'output_files'
os.makedirs(SAVE_FOLDER, exist_ok=True)

def convert_markdown_to_plain_text(md_content):
    html = markdown.markdown(md_content)
    soup = BeautifulSoup(html, 'html.parser')
    return soup.get_text()

def update_jira_issue_description(issue_key : str, md_content : str) -> str:
    with open("credentials.json", "r") as file:
        credentials = json.load(file)
    jira = Jira(url=credentials["base_url"], 
            username = credentials["username"],
            password = credentials["password"],
            cloud=True)
    issue = jira.issue(issue_key)
    current_description = issue['fields'].get('description', '')
    plain_text_description = current_description + convert_markdown_to_plain_text(md_content)

    update_fields = {
        'description': plain_text_description
    }
    jira.update_issue_field(issue_key, update_fields)
    return "Updated the description successfully"

def create_or_update_issue(fields: dict) -> dict:
    with open("credentials.json", "r") as file:
        credentials = json.load(file)
    jira = Jira(url=credentials["base_url"], 
            username = credentials["username"],
            password = credentials["password"],
            cloud=True)
    return jira.issue_create_or_update(fields)

def update_issue_field(key: str, fields: dict) -> str:
    with open("credentials.json", "r") as file:
        credentials = json.load(file)
    jira = Jira(url=credentials["base_url"], 
            username = credentials["username"],
            password = credentials["password"],
            cloud=True)
    return jira.update_issue_field(key, fields, notify_users=True)

user_proxy = autogen.UserProxyAgent(
    name="user_proxy",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=25,
    is_termination_msg=lambda msg: "TERMINATE" in msg["content"] if msg and msg.get("content") else None,
    code_execution_config= False,
    llm_config=llm_config,
)

system_message = """
You are a JIRA assistant capable of performing the following functions: creating EPICs, creating stories or tasks under an EPIC, and creating subtasks for each story or task. Your primary objective is to assist users in efficiently managing and retrieving information from JIRA, ensuring all provided information is accurate and reliable.

Please ensure that:

1. You must strictly perform operations solely by invoking the functions explicitly available to you, without attempting actions beyond these predefined capabilities.
2. If a request cannot be fulfilled using the available functions, promptly inform the user of this limitation, refraining from guessing or generating fabricated responses.
3. Ensure all responses are grounded in actual data obtained via the registered functions, maintaining accuracy and reliability.
4. Upon completing a task, respond with the word 'TERMINATE' to clearly indicate the conclusion of the process.

Follow these detailed steps to create an EPIC, associated stories, and corresponding subtasks:

1. **Analyze the Technical Analysis**:
   - Extract key details:
     - *Summary*: Identify the main goal or objective. If unclear, generate a draft summary.
     - *Description*: Provide an overview of technical components, including data sources, transformations, and outputs.
     - *Acceptance Criteria*: Infer or generate criteria based on the task's nature (e.g., "Data should be processed without errors") only for story creation.

2. **Create the EPIC**:
   - Utilize the extracted summary, description, and acceptance criteria to create a new EPIC in JIRA.
   - Don't use customfield_10080 field for Epic creation
   - Once creation of Epic was done, then go to next step


3. **Create Four Child User Stories**:
   - Develop four user stories encompassing:
     1. *Data Sources*: Details of input sources.
     2. *Transformations*: Steps for data transformation.
     3. *Custom Calculations*: Specifics of custom calculations.
     4. *Outputs*: Expected outputs and their structure.
   - Link these user stories to the EPIC created in step 2 as their parent.

4. **Create Subtasks**:
   - It is mandatory to create at least one subtask for each user story:
     - *Data Sources*: Create one subtask for each data source.
     - *Transformations*: Create one subtask for each transformation step.
     - *Custom Calculations*: Create one subtask for each unique calculation.
     - *Outputs*: Create one subtask for each output format or requirement.
   - Link each subtask to its respective user story created in step 3.
   issue type for subtasks is "Subtask"
   Don't use customfield_10080 field for Epic creation

Your adherence to these guidelines ensures the efficient and accurate management of JIRA tasks.
Ensure Epic, Stories and all substasks are created and linked. Return the Epic id.
Upon completing a task, respond with the word 'TERMINATE' to clearly indicate the conclusion of the process.
Only provide the output as example upon completion:
    1. "The Epic has been successfully created with the Epic key ID: **GA-3735** (Epic id from step 2)."
    2. "The Epic has been successfully created with the Epic key ID: **GA-3745** (Epic id from step 2)."
"""

JIRA_chatbot = autogen.AssistantAgent(
    name="JIRA_chatbot",
    system_message=system_message,
    is_termination_msg=lambda msg: "TERMINATE" in msg["content"],
    llm_config=llm_config,
)   

register_function(create_or_update_issue, caller = JIRA_chatbot, executor= user_proxy, name = 'create_or_update_issue',
                description= "Create the Epic, Story/issue and subtask issue with its fields like summary, description. The fields arugment takes the dictionary as input argument.")

register_function(update_issue_field, caller = JIRA_chatbot, executor= user_proxy, name = 'update_issue_field',
                description= "Tool to update issue fields like assign, summary, description, issuetype. It takes project key and fields as input")

def flatten_dict(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    items.extend(flatten_dict(item, f"{new_key}_{i}", sep=sep).items())
                else:
                    items.append((f"{new_key}_{i}", item))
        else:
            items.append((new_key, v))
    return dict(items)
    
def json_to_excel(data, output_file):
    with pd.ExcelWriter(output_file) as writer:
        for key, value in data.items():
            if isinstance(value, list) and len(value) > 0:
                if isinstance(value[0], dict):
                    flattened_data = [flatten_dict(item) for item in value]
                    df = pd.DataFrame(flattened_data)
                else:
                    df = pd.DataFrame(value)
            elif isinstance(value, dict):
                flattened_data = flatten_dict(value)
                df = pd.DataFrame([flattened_data])
            else:
                df = pd.DataFrame([value], columns=[key])
            df.to_excel(writer, sheet_name=key[:31], index=False)

def save_files(Technical_analysis, response, file_name):
    SAVE_FOLDER = 'output_files'
    try:
        Technical_analysis = convert_markdown_to_plain_text(Technical_analysis)
        with open(os.path.join(SAVE_FOLDER, file_name + '_Technical_analysis.txt'), 'w') as f:
            f.write(f"{Technical_analysis}")

        json_to_excel(response, os.path.join(SAVE_FOLDER,file_name + '_response.xlsx'))

        print("Files saved successfully.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving files: {str(e)}")

def upload_to_jira(jira_story, file_name):
    SAVE_FOLDER = 'output_files'
    with open("credentials.json", "r") as file:
        credentials = json.load(file)
    try:
        jira = Jira(url=credentials["base_url"], 
            username = credentials["username"],
            password = credentials["password"],
            cloud=True)

        files = [
            os.path.join(SAVE_FOLDER, file_name + '_Technical_analysis.txt'),
            os.path.join(SAVE_FOLDER, file_name + '_response.xlsx'),
        ]

        for file in files:
            jira.add_attachment(jira_story, file)
            print(f"{file} uploaded to JIRA story {jira_story}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading to JIRA: {str(e)}")

@app.get("/health")
async def health_check():
    return JSONResponse(status_code=200, content={"status": "healthy"})
    
@app.post("/JIRA/")
async def submit_string(username: str, password: str, base_url: str):
    msg = ""
    try:
        url = f'{base_url}/rest/api/2/myself'
        response = requests.get(url, auth=HTTPBasicAuth(username, password))
        if response.status_code == 200:
            msg = "Authentication successful"
            credentials = {'username' : username, 'password' : password, 'base_url': base_url}
            with open("credentials.json", "w") as file:
                json.dump(credentials, file)
            boards_url = f"{base_url}/rest/agile/1.0/board"
            boards_response = requests.get(boards_url, auth=HTTPBasicAuth(username, password))

            if boards_response.status_code == 200:
                boards = []
                boards_data = boards_response.json()
                boards_data = boards_data.get("values", [])
                for board_data in boards_data:
                    boards.append(board_data["location"]["displayName"])
                return {"message": msg, "boards": boards}
            else:
                return {"message": msg, "boards_error": "Failed to fetch boards"}

        else:
            raise HTTPException(status_code=401, detail="Invalid Credentials")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat(data: Inputprompt):
    PROJECTKEY = data.board_id
    basic_prompt = f"""Below is a Technical Analysis. Use it to create an Epic and its associated User Stories in the {PROJECTKEY} board. Include all required fields to avoid errors. 
    1. Analyse the Technical Analysis 
        Extract key details:  
        Summary: Main goal or objective. Generate a draft if unclear. 
        Description: Overview of technical components (data sources, transformations, outputs). 
        Acceptance Criteria: Infer or generate based on task nature (e.g., "Data should be processed without errors"). 
    2. Create the Epic 
        Project Key: {PROJECTKEY} 
        Issue Type: Epic 
        Summary: From main goal in the analysis 
        Description: High-level details from the analysis 
    3. Create 4 Child User Stories 
        Create 4 user stories covering: 
        Data Sources - Details of input sources 
        Transformations - Data transformation steps 
        Custom Calculations - Custom calculation details 
        Outputs - Expected outputs and structure 
        For each User Story: 
            Project Key: {PROJECTKEY} 
            Issue Type: Story 
            Summary: Short task description 
            Description: Detailed task info from analysis 
            customfield_10080 (Acceptance Criteria): Clear, specific success conditions 
            Parent: Link to Epic key 
    4. Create Sub-Tasks:  
        Mandatory: Create at least one sub-task for each User Story. 
        (Do NOT skip this step.) 
            Data Sources: Create one sub-task for each data source. 
            Transformations: Create one sub-task for each transformation step. 
            Custom Calculations: Create one sub-task for each unique calculation. 
            Outputs: Create one sub-task for each output format or requirement. 
            For each Sub-Task: 
            Project Key: {PROJECTKEY} 
            Issue Type: Subtask 
            Summary: Short task description 
            Description: Details from analysis 
            Parent: Link to User Story 
    5. Parent-Child Linking 
        Link User Stories to Epic and Sub-Tasks to User Stories. 
    6. Output 
        Return only the Epic key ID after successful creation. 
    Notes: 
        Include all required fields (e.g., priority, labels). 
        If details are missing, use placeholders or ask for clarification. 
        Ensure successful creation before returning the Epic key ID 
    Example upon completion:
    1. "The Epic has been successfully created with the Epic key ID: **GA-3735** (Epic id from step 2)."
    2. "The Epic has been successfully created with the Epic key ID: **GA-3745** (Epic id from step 2).
    Technical Analysis:
    """
    
    try:
        user_proxy.initiate_chat(
            JIRA_chatbot,
            message = basic_prompt + data.prompt,
            llm_config=llm_config,
        )
        final_msg = user_proxy.last_message()['content']
        if "TERMINATE" in final_msg:
            final_msg = final_msg.replace("TERMINATE", "")
        return final_msg
    except Exception as error:
        return f"error while doing the {data.prompt} : {error}"

@app.post("/upload-to-jira/")
async def handle_request(data: InputData):
    try:
        save_files(data.Technical_analysis, data.response_input, data.file_name)
        upload_to_jira(data.jira_story_id, data.file_name)
        update_jira_issue_description(data.jira_story_id, data.Executive_summary)
        return {"status": "success", "message": "Files uploaded to JIRA successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
