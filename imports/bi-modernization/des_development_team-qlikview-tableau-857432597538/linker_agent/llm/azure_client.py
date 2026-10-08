"""
Azure OpenAI Chat Client

Simple wrapper for Azure OpenAI API calls used in semantic matching.
"""

import os
from openai import AsyncAzureOpenAI
from typing import Optional


class AgentResponse:
    """Response from agent run"""
    def __init__(self, text: str):
        self.text = text
    
    def __str__(self):
        return self.text


class Agent:
    """Simple agent wrapper for LLM calls"""
    def __init__(self, client: AsyncAzureOpenAI, deployment_name: str, instructions: str):
        self.client = client
        self.deployment_name = deployment_name
        self.instructions = instructions

    async def run(self, prompt: str) -> AgentResponse:
        """Run the agent with a prompt"""
        messages = [
            {"role": "system", "content": self.instructions},
            {"role": "user", "content": prompt}
        ]

        response = await self.client.chat.completions.create(
            model=self.deployment_name,
            messages=messages,
            max_completion_tokens=2000
        )

        text = response.choices[0].message.content
        return AgentResponse(text)


class AzureOpenAIChatClient:
    """Azure OpenAI Chat Client wrapper"""
    
    def __init__(
        self,
        endpoint: str,
        deployment_name: str,
        api_key: str,
        api_version: str = "2024-02-15-preview"
    ):
        self.endpoint = endpoint
        self.deployment_name = deployment_name
        self.api_key = api_key
        self.api_version = api_version
        
        self.client = AsyncAzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=endpoint
        )
    
    def create_agent(self, name: str, instructions: str) -> Agent:
        """Create an agent with specific instructions"""
        return Agent(
            client=self.client,
            deployment_name=self.deployment_name,
            instructions=instructions
        )
