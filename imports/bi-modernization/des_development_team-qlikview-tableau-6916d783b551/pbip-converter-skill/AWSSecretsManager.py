import os
import json
import boto3
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig

class SecretsManagerClient:
    """
    A client class for interacting with AWS Secrets Manager, utilizing a caching layer for efficiency.

    Attributes:
        client (boto3.client): The Secrets Manager client used to interact with AWS Secrets Manager.
        cache (SecretCache): The cache used to store and manage secrets for quicker access.
    """

    def __init__(self, AWS_PROFILE_NAME, AWS_SECRET_NAME, AWS_REGION_NAME):
        """
        Initializes the SecretsManagerClient with AWS credentials, profile, and region details.

        Args:
            AWS_PROFILE_NAME (str): The name of the AWS profile to use for session creation.
            AWS_SECRET_NAME (str): The name of the secret to be accessed.
            AWS_REGION_NAME (str): The AWS region where the secret is stored.
        """
        # session = boto3.session.Session(profile_name=AWS_PROFILE_NAME)

        # Initialize a Secrets Manager client for the specified AWS region
        self.client = boto3.client(service_name='secretsmanager', region_name=AWS_REGION_NAME)

        # Set up cache configuration for efficient secret retrieval
        cache_config = SecretCacheConfig()

        # Initialize the secret cache with the configured client
        self.cache = SecretCache(config=cache_config, client=self.client)

        # Initialize the secret name
        self.secret_name = AWS_SECRET_NAME

    def get_all_secrets(self):
        """
        Retrieves the secret value from AWS Secrets Manager, using caching for efficiency.

        Args:
            secret_name (str): The name of the secret to retrieve.

        Returns:
            dict: The secret's value as a dictionary, or None if the secret is not found or an error occurs.
        """
        try:
            # Retrieve the secret value from the cache, falling back to Secrets Manager if necessary
            secret_string = self.cache.get_secret_string(self.secret_name)
            return json.loads(secret_string) if secret_string else None
        except self.client.exceptions.ResourceNotFoundException:
            # Handle the case where the secret does not exist
            print(f"The requested secret {self.secret_name} was not found.")
        except Exception as e:
            # Handle any other exceptions that may occur
            print(f"An error occurred while retrieving the secret: {str(e)}")
        return None

    def load_secrets_to_env(self):
        """
        Loads environment variables from the specified secret into the current environment.

        Args:
            secret_name (str): The name of the secret to load into environment variables.
        """
        try:
            # Retrieve the secret containing the environment variables
            secrets = self.get_all_secrets()
            if secrets:
                # Set each secret key-value pair as an environment variable
                for sec_name, sec_value in secrets.items():
                    os.environ[sec_name] = sec_value

                print("Environment variables loaded successfully.")
            else:
                # Handle case where no secrets were found under the specified name
                print(f"No secrets found under the name {self.secret_name}.")

        except Exception as e:
            # Handle any errors that may occur during the loading process
            print(f"An unexpected error occurred while loading environment variables: {e}")

    def retrieve_key_names(self):
        """
        Retrieves the names of all keys stored in the specified secret.

        Args:
            secret_name (str): The name of the secret to retrieve key names from.

        Returns:
            list: A list of key names in the secret, or an empty list if an error occurs.
        """
        try:
            # Retrieve the secret and return the list of keys
            secrets = self.get_all_secrets()
            return list(secrets.keys()) if secrets else []
        except Exception as e:
            # Handle any errors that may occur during key retrieval
            print(f"An unexpected error occurred while retrieving key names: {e}")
            return []

    def get_value_for_secret_key(self, secret_key):
        """
        Retrieves the value of a specific key from the specified secret.

        Args:
            secret_name (str): The name of the secret to retrieve the key from.
            secret_key (str): The key to retrieve the value for.

        Returns:
            str: The value of the specified key, or None if an error occurs or the key is not found.
        """
        try:
            # Retrieve the secret and return the value associated with the specified key
            secrets = self.get_all_secrets()
            return secrets.get(secret_key) if secrets else None
        except Exception as e:
            # Handle any errors that may occur during value retrieval
            print(f"An unexpected error occurred while retrieving the value for {secret_key}: {e}")
            return None

    def get_batch_values_for_secret_keys(self, secret_keys):
        """
        Retrieves the values of multiple keys from the specified secret.

        Args:
            secret_name (str): The name of the secret to retrieve the keys from.
            secret_keys (list): A list of keys to retrieve values for.

        Returns:
            dict: A dictionary containing the specified keys and their corresponding values, or an empty dictionary if an error occurs.
        """
        try:
            # Retrieve the secret and return a dictionary of requested key-value pairs
            secrets = self.get_all_secrets()
            if secrets:
                return {key: secrets.get(key) for key in secret_keys}
            else:
                print(f"No secrets found under the name {self.secret_name}.")
                return {}
        except Exception as e:
            # Handle any errors that may occur during the process
            print(f"An unexpected error occurred while retrieving values: {e}")
            return {}
