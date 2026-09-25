from __future__ import annotations

from typing import Any

import botocore.session
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials


class SigV4Session(requests.Session):
    """Session requests qui signe chaque requête en SigV4 (OTLP vers CloudWatch / X-Ray)."""

    def __init__(self, region: str, service: str, credentials: Credentials | None = None) -> None:
        super().__init__()
        self.region = region
        self.service = service
        self._credentials = credentials or botocore.session.Session().get_credentials()

    def request(
        self, method: str, url: str | bytes, *args: Any, **kwargs: Any
    ) -> requests.Response:
        headers = {**self.headers, **(kwargs.pop("headers", None) or {})}
        data = kwargs.pop("data", None)
        aws = AWSRequest(method=method, url=str(url), data=data, headers=headers)
        SigV4Auth(self._credentials.get_frozen_credentials(), self.service, self.region).add_auth(
            aws
        )
        return super().request(
            method, url, *args, data=data, headers=dict(aws.headers.items()), **kwargs
        )
