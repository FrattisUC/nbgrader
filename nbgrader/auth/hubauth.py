"""JupyterHub authenticator."""
import requests
import os
import json
from subprocess import check_output
from flask import request, redirect, abort
from traitlets import Unicode, Int, List, Bool
from six.moves.urllib.parse import unquote

from nbgrader.formgrader.formgrade import blueprint
from .base import BaseAuth


class HubAuth(BaseAuth):
    """Jupyter hub authenticator."""

    graders = List([], config=True, help="List of JupyterHub user names allowed to grade.")

    proxy_address = Unicode(config=True, help="Address of the configurable-http-proxy server.")
    def _proxy_address_default(self):
        return self._ip
    proxy_port = Int(8001, config=True, help="Port of the configurable-http-proxy server.")

    hub_address = Unicode(config=True, help="Address of the hub server.")
    def _hub_address_default(self):
        return self._ip
    hub_port = Int(8000, config=True, help="Port of the hub server.")
    
    hubapi_address = Unicode(config=True, help="Address of the hubapi server.")
    def _hubapi_address_default(self):
        return self._ip
    hubapi_port = Int(8081, config=True, help="Port of the hubapi server.")
    hubapi_cookie = Unicode("jupyter-hub-token", config=True, help="Name of the cookie used by JupyterHub")

    notebook_url_prefix = Unicode(None, config=True, allow_none=True, help="""
        Relative path of the formgrader with respect to the hub's user base
        directory.  No trailing slash. i.e. "Documents" or "Documents/notebooks". """)
    def _notebook_url_prefix_changed(self, name, old, new):
        self.notebook_url_prefix = new.strip('/')
    
    hub_base_url = Unicode(config=True, help="Base URL of the hub server.")
    def _hub_base_url_default(self):
        return 'http://{}:{}'.format(self.hub_address, self.hub_port)
    
    generate_hubapi_token = Bool(False, config=True, help="""Use `jupyterhub token` as a default
        for HubAuth.hubapi_token instead of $JPY_API_TOKEN.""")
    hubapi_token_user = Unicode('', config=True, help="""The user for which to obtain
        a jupyterhub token. Only used if `generate_hubapi_token` is True.""")

    hub_db = Unicode(config=True, help="""Path to JupyterHub's database.  Only
        manditory if `generate_hubapi_token` is True.""")

    hubapi_token = Unicode(config=True, help="""JupyterHub API auth token.  
        Generated by running `jupyterhub token`.  If not explicitly set,
        nbgrader will use $JPY_API_TOKEN as the API token.""")
    def _hubapi_token_default(self):
        if self.generate_hubapi_token:
            cmd = ['jupyterhub', 'token', '--db={}'.format(self.hub_db)]
            if self.hubapi_token_user:
                cmd.append(self.hubapi_token_user)
            return check_output(cmd).decode('utf-8').strip()
        else:
            return os.environ.get('JPY_API_TOKEN', '')

    proxy_token = Unicode(config=True, help="""JupyterHub configurable proxy 
        auth token.  If not explicitly set, nbgrader will use 
        $CONFIGPROXY_AUTH_TOKEN as the API token.""")
    def _proxy_token_default(self):
        return os.environ.get('CONFIGPROXY_AUTH_TOKEN', '')

    remap_url = Unicode(config=True, help="""Suffix appened to 
        `HubAuth.hub_base_url` to form the full URL to the formgrade server.  By
        default this is '/hub/{NbGrader.course_id}'.  Change this if you
        plan on running more than one formgrade server behind one JupyterHub
        instance.""")
    def _remap_url_default(self):
        return '/hub/nbgrader/' + self.parent.course_id
    def _remap_url_changed(self, name, old, new):
        self.remap_url = new.rstrip('/')

    connect_ip = Unicode('', config=True, help="""The formgrader ip address that
        JupyterHub should actually connect to. Useful for when the formgrader is
        running behind a proxy or inside a container.""")

    notebook_server_user = Unicode('', config=True, help="""The user that hosts
        the autograded notebooks. By default, this is just the user that is logged
        in, but if that user is an admin user and has the ability to access other
        users' servers, then this variable can be set, allowing them to access
        the notebook server with the autograded notebooks.""")

    def __init__(self, *args, **kwargs):
        super(HubAuth, self).__init__(*args, **kwargs)

        # Create base URLs for the hub and proxy.
        self._hubapi_base_url = 'http://{}:{}'.format(self.hubapi_address, self.hubapi_port)
        self._proxy_base_url = 'http://{}:{}'.format(self.proxy_address, self.proxy_port)

        # Register self as a route of the configurable-http-proxy and then
        # update the base_url to point to the new path.
        if self.connect_ip:
            ip = self.connect_ip
        else:
            ip = self._ip
        target = 'http://{}:{}'.format(ip, self._port)
        self.log.info("Proxying {} --> {}".format(self.remap_url, target))
        response = self._proxy_request('/api/routes' + self.remap_url, method='POST', body={
            'target': target
        })
        # This error will occur, for example, if the CONFIGPROXY_AUTH_TOKEN is
        # incorrect.
        if response.status_code != 201:
            raise Exception('Error while trying to add JupyterHub route. {}: {}'.format(response.status_code, response.text))
        self._base_url = self.hub_base_url + self.remap_url

        # Redirect all formgrade request to the correct API method.
        self._app.register_blueprint(blueprint, static_url_path=self.remap_url + '/static', url_prefix=self.remap_url, url_defaults={'name': 'hub'})

    def authenticate(self):
        """Authenticate a request.
        Returns a boolean or flask redirect."""

        # If auth cookie doesn't exist, redirect to the login page with
        # next set to redirect back to the this page.
        if 'jupyter-hub-token' not in request.cookies:
            return redirect(self.hub_base_url + '/hub/login?next=' + self.remap_url)
        cookie = request.cookies[self.hubapi_cookie]

        # Check with the Hub to see if the auth cookie is valid.
        response = self._hubapi_request('/hub/api/authorizations/cookie/' + self.hubapi_cookie + '/' + cookie)
        if response.status_code == 200:

            #  Auth information recieved.
            data = response.json()
            if 'name' in data:
                user = data['name']

                # Check if the user name is registered as a grader.
                if user in self.graders:
                    self._user = user
                    return True
                else:
                    self.log.warn('Unauthorized user "%s" attempted to access the formgrader.' % user)

            # this shouldn't happen, but possibly might if the JupyterHub API
            # ever changes
            else:
                self.log.warn('Malformed response from the JupyterHub auth API.')
                abort(500, "Failed to check authorization, malformed response from Hub auth.")

        # this will happen if the JPY_API_TOKEN is incorrect
        elif response.status_code == 403:
            self.log.error("I don't have permission to verify cookies, my auth token may have expired: [%i] %s", response.status_code, response.reason)
            abort(500, "Permission failure checking authorization, I may need to be restarted")

        # this will happen if jupyterhub has been restarted but the user cookie
        # is still the old one, in which case we should reauthenticate
        elif response.status_code == 404:
            self.log.warn("Failed to check authorization, this probably means the user's cookie token is invalid or expired: [%i] %s", response.status_code, response.reason)
            return redirect(self.hub_base_url + '/hub/login?next=' + self.remap_url)

        # generic catch-all for upstream errors
        elif response.status_code >= 500:
            self.log.error("Upstream failure verifying auth token: [%i] %s", response.status_code, response.reason)
            abort(502, "Failed to check authorization (upstream problem)")

        # generic catch-all for internal server errors
        elif response.status_code >= 400:
            self.log.warn("Failed to check authorization: [%i] %s", response.status_code, response.reason)
            abort(500, "Failed to check authorization")

        else:
            # Auth invalid, reauthenticate.
            return redirect(self.hub_base_url + '/hub/login?next=' + self.remap_url)

        return False

    def notebook_server_exists(self):
        """Does the notebook server exist?"""
        if self.notebook_server_user:
            user = self.notebook_server_user
        else:
            user = self._user

        # first check if the server is running
        response = self._hubapi_request('/hub/api/users/{}'.format(user))
        if response.status_code == 200:
            user_data = response.json()
        else:
            self.log.warn("Could not access information about user {} (response: {} {})".format(
                user, response.status_code, response.reason))
            return False

        # start it if it's not running
        if user_data['server'] is None and user_data['pending'] != 'spawn':
            # start the server
            response = self._hubapi_request('/hub/api/users/{}/server'.format(user), method='POST')
            if response.status_code not in (201, 202):
                self.log.warn("Could not start server for user {} (response: {} {})".format(
                    user, response.status_code, response.reason))
                return False

        return True

    def get_notebook_server_cookie(self):
        # same user, so no need to request admin access
        if not self.notebook_server_user:
            return None

        # request admin access to the user's server
        response = self._hubapi_request('/hub/api/users/{}/admin-access'.format(self.notebook_server_user), method='POST')
        if response.status_code != 200:
            self.log.warn("Failed to gain admin access to user {}'s server (response: {} {})".format(
                self.notebook_server_user, response.status_code, response.reason))
            return None

        # access granted!
        cookie_name = '{}-{}'.format(self.hubapi_cookie, self.notebook_server_user)
        notebook_server_cookie = unquote(response.cookies[cookie_name][1:-1])
        cookie = {
            'key': cookie_name,
            'value': notebook_server_cookie,
            'path': '/user/{}'.format(self.notebook_server_user)
        }

        return cookie

    def get_notebook_url(self, relative_path):
        """Gets the notebook's url."""
        if self.notebook_url_prefix is not None:
            relative_path = self.notebook_url_prefix + '/' + relative_path
        if self.notebook_server_user:
            user = self.notebook_server_user
        else:
            user = self._user
        return "{}/user/{}/notebooks/{}".format(self.hub_base_url, user, relative_path)

    def _hubapi_request(self, *args, **kwargs):
        return self._request('hubapi', *args, **kwargs)

    def _proxy_request(self, *args, **kwargs):
        return self._request('proxy', *args, **kwargs)

    def _request(self, service, relative_path, method='GET', body=None):
        base_url = getattr(self, '_%s_base_url' % service)
        token = getattr(self, '%s_token' % service)

        data = body
        if isinstance(data, (dict,)):
            data = json.dumps(data)

        return requests.request(method, base_url + relative_path, headers={
            'Authorization': 'token %s' % token
        }, data=data)
