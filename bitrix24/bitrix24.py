#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Wrapper over Bitrix24 cloud API"""

import time
import logging

import requests
from multidimensional_urlencode import urlencode

from .exceptions import *


_all__ = ('Bitrix24', )


class Bitrix24(object):
    """Class for working with Bitrix24 cloud API"""
    # Bitrix24 API endpoint
    api_url = '%s/rest/%s.json'
    # Bitrix24 oauth server
    oauth_url = 'https://oauth.bitrix.info/oauth/token/'
    # Timeout for API request in seconds
    timeout = 60

    _is_tokens_refreshed = False

    def __init__(self, domain, access_token=None, refresh_token='', client_id='',
                 client_secret='', code=None, custom_oauth_url=None):
        """Create Bitrix24 API object
        :param domain: str Bitrix24 domain
        :param access_token: str Auth token
        :param refresh_token: str Refresh token
        :param client_id: str Client ID for refreshing access tokens
        :param client_secret: str Client secret for refreshing access tokens
        :param code: str App code retrieved via first authentication
        :param custom_oauth_url: str Custom oAuth2 server ULR
        """
        self.domain = domain
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.code = code
        if custom_oauth_url is not None:
            self.oauth_url = custom_oauth_url

        if (not self.access_token and not self.refresh_token) and not self.code:
            raise ValueError('You should pass auth_token or auth code.')

    def call(self, method, params1=None, params2=None, params3=None, params4=None):
        """Call Bitrix24 API method
        :param method: Method name
        :param params1: Method parameters 1
        :param params2: Method parameters 2. Needed for methods with determinate consequence of parameters
        :param params3: Method parameters 3. Needed for methods with determinate consequence of parameters
        :param params4: Method parameters 4. Needed for methods with determinate consequence of parameters
        :return: Call result
        """

        # Checking token exists
        if not self.access_token:
            if self.refresh_token:
                self.refresh_tokens()
            else:
                self.authenticate()

        if method == '' or not isinstance(method, str):
            raise Exception('Empty Method')

        if method == 'batch' and 'prepared' not in params1:
            params1['cmd'] = self.prepare_batch(params1['cmd'])
            params1['prepared'] = True

        encoded_parameters = ''

        # print params1
        for i in [params1, params2, params3, params4, {'auth': self.access_token}]:
            if i is not None:
                if 'cmd' in i:
                    i = dict(i)
                    encoded_parameters += self.encode_cmd(i['cmd']) + '&' + urlencode({'halt': i['halt']}) + '&'
                else:
                    encoded_parameters += urlencode(i) + '&'
        r = {}

        try:
            # request url
            url = self.api_url % (self.domain, method)
            # Make API request
            r = requests.post(url, data=encoded_parameters, timeout=self.timeout)
            # Decode response
            result = r.json()
        except ValueError:
            result = dict(error='Error on decode api response [%s]' % r.text)
        except requests.ReadTimeout:
            result = dict(error='Timeout waiting expired [%s sec]' % str(self.timeout))
        except requests.ConnectionError as e:
            print(e.request.url)
            print(e)
            result = dict(error='Max retries exceeded [1]')
        except (AuthenticationFailed, TokenRenewFailed) as e:
            result = e.result
            if 'error' in result:
                error_code = result['error']
                if error_code in ('invalid_token', 'NO_AUTH_FOUND', 'expired_token'):
                    self.refresh_tokens()
                elif error_code in 'QUERY_LIMIT_EXCEEDED':
                    # Suspend call on two second, wait limitation time by Bitrix24 API
                    time.sleep(2)
                    return self.call(method, params1, params2, params3, params4)

                # Repeat API request after renew token
                result = self.call(method, params1, params2, params3, params4)

        return result

    def authenticate(self):
        """Retrieve access tokens
        :return:
        """
        try:
            # Make call to oauth server
            r = requests.post(
                self.oauth_url,
                params={
                    'grant_type': 'authorization_code',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'code': self.code
                })
            result = r.json()
            if r.status_code != 200:
                raise AuthenticationFailed(result=r.json(), status_code=r.status_code)
            # Retrieve access tokens
            self.access_token = result['access_token']
            self.refresh_token = result['refresh_token']
            logging.debug(['Tokens', self.access_token, self.refresh_token])
            self._is_tokens_refreshed = True
            return result

        except Exception as e:
            raise e

    def refresh_tokens(self):
        """Refresh access tokens
        :return:
        """
        try:
            # Make call to oauth server
            r = requests.post(
                self.oauth_url,
                params={
                    'grant_type': 'refresh_token',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'refresh_token': self.refresh_token
                }
            )
            result = r.json()
            if r.status_code != 200:
                raise TokenRenewFailed(result=r.json(), status_code=r.status_code)
            # Renew access tokens
            self.access_token = result['access_token']
            self.refresh_token = result['refresh_token']
            logging.info(['Tokens', self.access_token, self.refresh_token])
            self._is_tokens_refreshed = True
            return result
        except Exception as e:
            raise e

    @property
    def tokens(self):
        """Get access tokens
        :return: dict
        """
        return {'auth_token': self.access_token, 'refresh_token': self.refresh_token}

    @property
    def is_tokens_refreshed(self):
        return self._is_tokens_refreshed

    @staticmethod
    def prepare_batch(params):
        """
        Prepare methods for batch call
        :param params: dict
        :return: dict
        """
        if not isinstance(params, dict):
            raise Exception('Invalid \'cmd\' structure')

        batched_params = dict()

        for call_id in sorted(params.keys()):
            if not isinstance(params[call_id], list):
                raise Exception('Invalid \'cmd\' method description')
            method = params[call_id].pop(0)
            if method == 'batch':
                raise Exception('Batch call cannot contain batch methods')
            temp = ''
            for i in params[call_id]:
                temp += urlencode(i) + '&'
            batched_params[call_id] = method + '?' + temp

        return batched_params

    @staticmethod
    def encode_cmd(cmd):
        """Resort batch cmd by request keys and encode it
        :param cmd: dict List methods for batch request with request ids
        :return: str
        """
        cmd_encoded = ''

        for i in sorted(cmd.keys()):
            cmd_encoded += urlencode({'cmd': {i: cmd[i]}}) + '&'

        return cmd_encoded

    def batch(self, params):
        """Batch calling without limits. Method automatically prepare method for batch calling
        :param params:
        :return:
        """
        if 'halt' not in params or 'cmd' not in params:
            return dict(error='Invalid batch structure')

        result = dict()

        result['result'] = dict(
            result_error={},
            result_total={},
            result={},
            result_next={},
        )
        count = 0
        batch = dict()
        for request_id in sorted(params['cmd'].keys()):
            batch[request_id] = params['cmd'][request_id]
            count += 1
            if len(batch) == 49 or count == len(params['cmd']):
                temp = self.call('batch', {'halt': params['halt'], 'cmd': batch})
                for i in temp['result']:
                    if len(temp['result'][i]) > 0:
                        result['result'][i] = self.merge_two_dicts(temp['result'][i], result['result'][i])
                batch = dict()

        return result

    @staticmethod
    def merge_two_dicts(x, y):
        """Given two dicts, merge them into a new dict as a shallow copy."""
        z = x.copy()
        z.update(y)
        return z
