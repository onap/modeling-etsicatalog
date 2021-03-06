# Copyright (c) 2019, CMCC Technologies. Co., Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging

import requests

from catalog.pub.Dmaap_lib.pub.exceptions import DmaapClientException

requests.packages.urllib3.disable_warnings()
logger = logging.getLogger(__name__)


class IdentityClient:
    def __init__(self, base_url):
        self.base_url = base_url

    def create_apikey(self, email, description):
        try:
            headers = {'content-type': 'application/json;charset=UTF-8'}
            data = {
                'email': email,
                'description': description
            }
            data = json.JSONEncoder().encode(data)
            url = self.base_url + "/apiKeys/create"
            ret = requests.post(url=url, data=data, headers=headers, verify=False)
            logger.info('create apiKey, response status_code: %s, body: %s', ret.status_code, ret.json())
            if ret.status_code != 200:
                raise DmaapClientException(ret.json())
            ret = ret.json()
            resp_data = {
                'apiKey': ret.get('key', ''),
                'apiSecret': ret.get('secret', '')
            }
            return resp_data
        except Exception as e:
            raise DmaapClientException('create apikey from dmaap failed: ' + str(e))

    def get_apikey(self, apikey):
        try:
            url = self.base_url + "/apiKeys/%s" % apikey
            ret = requests.get(url)
            logger.info('get apiKey, response status_code: %s, body: %s', ret.status_code, ret.json())
            if ret.status_code != 200:
                raise DmaapClientException(ret.json())
            ret = ret.json()
            return ret
        except Exception as e:
            raise DmaapClientException('get apikey from dmaap failed: ' + str(e))

    def delete_apikey(self):
        pass

    def update_apikey(self, apikey, email, description):
        pass
