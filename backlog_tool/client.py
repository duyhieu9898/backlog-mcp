#!/usr/bin/env python3
import requests

from .settings import (
    REQUEST_TIMEOUT_SECONDS,
    api_base_url,
    log_event,
    require_api_key,
    response_error_body,
)


def log_response(method, path, response):
    if response.ok:
        log_event("info", "api", method=method, path=path, status=response.status_code)
    else:
        log_event(
            "error",
            "api",
            method=method,
            path=path,
            status=response.status_code,
            body=response_error_body(response),
        )


class BacklogClient:
    def __init__(self, config):
        self.config = config

    def request_json(self, method, path, data=None, params=None):
        request_params = {"apiKey": require_api_key()}
        if params:
            request_params.update(params)

        response = requests.request(
            method,
            f"{api_base_url(self.config)}{path}",
            params=request_params,
            data=data,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        log_response(method, path, response)
        try:
            response.raise_for_status()
        except requests.HTTPError as error:
            raise RuntimeError(
                f"{method} {path} failed with status {response.status_code}: {response_error_body(response)}"
            ) from error
        return response.json()

    def get_project_id(self, project):
        if project.get("id"):
            return project["id"]
        return self.request_json("GET", f"/projects/{project['key']}")["id"]

    def get_issue(self, issue_id):
        return self.request_json("GET", f"/issues/{issue_id}")

    def get_issues(
        self,
        project_id,
        query=None,
        assignee_id=None,
        status_ids=None,
        issue_type_ids=None,
        count=100,
        offset=0,
        sort=None,
        order=None,
    ):
        params = {
            "projectId[]": [project_id],
            "count": count,
            "offset": offset,
        }
        if query:
            params["keyword"] = query
        if assignee_id:
            params["assigneeId[]"] = [assignee_id]
        if status_ids:
            params["statusId[]"] = status_ids
        if issue_type_ids:
            params["issueTypeId[]"] = issue_type_ids
        if sort:
            params["sort"] = sort
        if order:
            params["order"] = order
        return self.request_json("GET", "/issues", params=params)

    def create_issue(self, payload):
        return self.request_json("POST", "/issues", data=payload)

    def update_issue(self, issue_id, payload):
        return self.request_json("PATCH", f"/issues/{issue_id}", data=payload)

    def get_priorities(self):
        return self.request_json("GET", "/priorities")

    def get_project_statuses(self, project_key):
        return self.request_json("GET", f"/projects/{project_key}/statuses")

    def get_project(self, project_key):
        return self.request_json("GET", f"/projects/{project_key}")

    def get_issue_types(self, project_key):
        return self.request_json("GET", f"/projects/{project_key}/issueTypes")

    def get_categories(self, project_key):
        return self.request_json("GET", f"/projects/{project_key}/categories")

    def get_custom_fields(self, project_key):
        return self.request_json("GET", f"/projects/{project_key}/customFields")
