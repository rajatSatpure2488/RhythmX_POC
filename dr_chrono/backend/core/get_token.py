"""
Create and reuse an EHR OAuth token.

All configuration is loaded in dr_chrono/config.py from dr_chrono/.env.
This script is independent. It does not import or use any MediSync files.
"""

import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests
from loguru import logger

try:
    from .config import ENV_FILE, settings
except ImportError:
    from  dr_chrono.backend.core.config import ENV_FILE, settings


class EHRTokenError(Exception):
    def __init__(self, error):
        self.error = error
        super().__init__(f"EHR token request failed: {error}")


ACCESS_TOKEN_KEY = "access_token"
REFRESH_TOKEN_KEY = "refresh_token"
LOCAL_EXPIRES_AT_KEY = "local_expires_at"
LOCAL_EXPIRES_IN_KEY = "local_expires_in"
LOCAL_EXPIRES_AT_ISO_KEY = "local_expires_at_iso"


class TokenHandler:
    def __init__(self, ehr_settings=settings):
        self.settings = ehr_settings
        logger.debug("TokenHandler initialized for EHR={}", self.get_config("EHR_NAME", "unknown"))

    def get_config(self, name, default=""):
        value = getattr(self.settings, name, default)
        if value is None:
            return default
        return value

    def require_config(self, name):
        value = self.get_config(name)
        if value == "":
            logger.error("Missing required token configuration: {}", name)
            raise ValueError(f"{name} is missing in {ENV_FILE}")
        return value

    def get_token_file(self):
        token_file = self.settings.TOKEN_FILE_PATH
        logger.debug("Resolved token file path: {}", token_file)
        return token_file

    def get_expiry_seconds(self):
        return self.require_config("EHR_LOCAL_TOKEN_EXPIRY_SECONDS")

    def load_saved_token(self):
        token_file = self.get_token_file()
        if not token_file.exists():
            logger.info("Token file does not exist yet: {}", token_file)
            return None

        try:
            token = json.loads(token_file.read_text(encoding="utf-8"))
            logger.info("Loaded saved token from file.")
            return token
        except json.JSONDecodeError:
            logger.error("Token file is not valid JSON: {}", token_file)
            return None

    def is_saved_token_valid(self, token):
        if not token:
            logger.debug("No saved token available for validity check.")
            return False

        if not token.get(ACCESS_TOKEN_KEY):
            logger.info("Saved token is missing access token.")
            return False

        expires_at = token.get(LOCAL_EXPIRES_AT_KEY)
        if not expires_at:
            logger.info("Saved token is missing local expiry.")
            return False

        is_valid = int(time.time()) < int(expires_at)
        if is_valid:
            logger.success("Saved token is valid.")
        else:
            logger.info("Saved token is expired.")
        return is_valid

    def post_token_request(self, payload):
        logger.info("Requesting EHR token using grant type: {}", payload.get("grant_type"))
        response = requests.post(
            self.require_config("EHR_TOKEN_URL"),
            data=payload,
            timeout=self.require_config("EHR_REQUEST_TIMEOUT_SECONDS"),
        )
        logger.debug("EHR token endpoint responded with status code: {}", response.status_code)
        return self.read_ehr_response(response)

    def create_token_with_auth_code(self):
        auth_code = self.get_config("EHR_AUTH_CODE")
        if not auth_code:
            logger.debug("EHR_AUTH_CODE not configured; skipping auth-code token flow.")
            return None
        logger.info("Creating token with auth-code flow.")

        payload = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.require_config("EHR_REDIRECT_URI"),
            "client_id": self.require_config("EHR_CLIENT_ID"),
            "client_secret": self.require_config("EHR_CLIENT_SECRET"),
        }

        return self.post_token_request(payload)

    def create_token_with_refresh_token(self, refresh_token=None):
        refresh_token = refresh_token or self.get_config("EHR_REFRESH_TOKEN")
        if not refresh_token:
            logger.debug("No refresh token available; skipping refresh flow.")
            return None
        logger.info("Creating token with refresh-token flow.")

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.require_config("EHR_CLIENT_ID"),
            "client_secret": self.require_config("EHR_CLIENT_SECRET"),
        }

        token = self.post_token_request(payload)
        token[REFRESH_TOKEN_KEY] = token.get(REFRESH_TOKEN_KEY) or refresh_token
        return token

    def create_token_with_login(self):
        username = self.get_config("EHR_USERNAME")
        password = self.get_config("EHR_PASSWORD")
        if not username or not password:
            logger.debug("EHR username/password not configured; skipping login token flow.")
            return None
        logger.info("Creating token with login flow.")

        payload = {
            "grant_type": "password",
            "username": username,
            "password": password,
            "client_id": self.require_config("EHR_CLIENT_ID"),
            "client_secret": self.require_config("EHR_CLIENT_SECRET"),
        }

        scope = self.get_config("EHR_SCOPE")
        if scope:
            payload["scope"] = scope

        return self.post_token_request(payload)

    def read_ehr_response(self, response):
        if response.status_code == 200:
            logger.success("EHR token request succeeded.")
            return response.json()

        try:
            error = response.json()
        except ValueError:
            error = response.text

        logger.error("EHR token request failed. status={} error={}", response.status_code, error)
        raise EHRTokenError(error)

    def get_authorization_url(self):
        logger.info("Building EHR authorization URL.")
        params = {
            "response_type": "code",
            "client_id": self.require_config("EHR_CLIENT_ID"),
            "redirect_uri": self.require_config("EHR_REDIRECT_URI"),
        }

        scope = self.get_config("EHR_SCOPE")
        if scope:
            params["scope"] = scope

        return f"{self.require_config('EHR_AUTH_URL')}?{urlencode(params)}"

    def add_local_expiry(self, token):
        logger.debug("Adding local token expiry metadata.")
        now = int(time.time())
        expires_at = now + self.get_expiry_seconds()

        token[LOCAL_EXPIRES_IN_KEY] = self.get_expiry_seconds()
        token[LOCAL_EXPIRES_AT_KEY] = expires_at
        token[LOCAL_EXPIRES_AT_ISO_KEY] = datetime.fromtimestamp(
            expires_at,
            tz=timezone.utc,
        ).isoformat()
        logger.info("Local token expiry set to {}", token[LOCAL_EXPIRES_AT_ISO_KEY])

        return token

    def save_token(self, token):
        token = self.add_local_expiry(token)
        self.get_token_file().write_text(json.dumps(token, indent=2), encoding="utf-8")
        logger.success("Token saved successfully to {}", self.get_token_file())
        return token

    def get_refresh_token_from_saved_file(self, saved_token):
        if not saved_token:
            logger.debug("No saved token found while looking for refresh token.")
            return ""

        refresh_token = saved_token.get(REFRESH_TOKEN_KEY, "")
        if refresh_token:
            logger.debug("Refresh token found in saved token file.")
        else:
            logger.info("Saved token does not contain refresh token.")
        return refresh_token

    def get_token(self):
        logger.info("Starting get_token flow.")
        saved_token = self.load_saved_token()
        if self.is_saved_token_valid(saved_token):
            logger.success("Using existing token from file.")
            return saved_token

        try:
            token = self.create_token_with_refresh_token(
                self.get_refresh_token_from_saved_file(saved_token)
            )
            if token:
                logger.success("Token file was expired. Created a new token with refresh token.")
                return self.save_token(token)
        except EHRTokenError as error:
            logger.error("Could not refresh saved token: {}", error.error)

        token = self.create_token_with_auth_code()
        if token:
            logger.success("Created a new token with auth code.")
            return self.save_token(token)

        try:
            token = self.create_token_with_refresh_token()
            if token:
                logger.success("Created a new token with refresh token from .env.")
                return self.save_token(token)
        except EHRTokenError as error:
            logger.error("Could not refresh token from .env: {}", error.error)

        token = self.create_token_with_login()
        if token:
            logger.success("Created a new token with login details.")
            return self.save_token(token)

        logger.error("Token could not be created from any configured flow.")
        return None


def main():
    handler = TokenHandler()
    ehr_name = handler.require_config("EHR_NAME")

    try:
        token = handler.get_token()
    except EHRTokenError as error:
        token = None
        logger.error("Could not create token from current {} .env values: {}", ehr_name, error.error)
        print(f"Could not create token from current {ehr_name} .env values.")
        print(f"{ehr_name} response: {error.error}")
        print("")
        if isinstance(error.error, dict) and error.error.get("error") == "unauthorized_client":
            print("This EHR app does not allow username/password token creation.")
            print("Use the OAuth URL below, login in the browser, then paste the code into EHR_AUTH_CODE.")
            print("")

    if token:
        logger.success("Token is ready for EHR={}", ehr_name)
        print("Token is ready.")
        print(f"Saved token file: {handler.get_token_file()}")
        print(f"Local expiry: {token[LOCAL_EXPIRES_AT_ISO_KEY]} UTC")
        print("")
        print("Access token:")
        print(token.get(ACCESS_TOKEN_KEY))
        return

    logger.error("Token was not created; authorization URL will be shown.")
    print("Token was not created.")
    print("")
    print(f"Use this {ehr_name} login URL to get an auth code:")
    print(handler.get_authorization_url())


if __name__ == "__main__":
    main()
