# Copyright 2019 ZTE Corporation.
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

import logging
import os
import base64


logger = logging.getLogger(__name__)

SECTIONS = (VDU_COMPUTE_TYPE, VNF_VL_TYPE, VDU_CP_TYPE, VDU_STORAGE_TYPE) = \
           ('tosca.nodes.nfv.Vdu.Compute', 'tosca.nodes.nfv.VnfVirtualLink', 'tosca.nodes.nfv.VduCp', 'tosca.nodes.nfv.Vdu.VirtualStorage')


class VnfdSOL251():

    def __init__(self, model):
        self.model = model

    def build_vnf(self, tosca):
        vnf = self.model.get_substitution_mappings(tosca)
        properties = vnf.get("properties", {})
        metadata = vnf.get("metadata", {})

        for key, value in list(properties.items()):
            if isinstance(value, dict):
                if value["type"] == "string":
                    properties[key] = value.get("default", "")
                elif value["type"] == "list":
                    properties[key] = value.get("default", {})
                else:
                    properties[key] = value.get("default", "")
        ptype = "descriptor_id"
        meta_types = ["descriptor_id", "id", "UUID"]
        self._get_property(properties, metadata, ptype, meta_types)

        ptype = "descriptor_version"
        meta_types = ["template_version", "version"]
        self._get_property(properties, metadata, ptype, meta_types)

        ptype = "provider"
        meta_types = ["template_author", "provider"]
        self._get_property(properties, metadata, ptype, meta_types)

        ptype = "template_name"
        meta_types = ["template_name"]
        self._get_property(properties, metadata, ptype, meta_types)

        ptype = "software_version"
        meta_types = ["software_version"]
        self._get_property(properties, metadata, ptype, meta_types)

        ptype = "product_name"
        meta_types = ["product_name"]
        self._get_property(properties, metadata, ptype, meta_types)

        ptype = "flavour_description"
        meta_types = ["flavour_description"]
        self._get_property(properties, metadata, ptype, meta_types)

        ptype = "vnfm_info"
        meta_types = ["vnfm_info"]
        self._get_property(properties, metadata, ptype, meta_types)

        ptype = "flavour_id"
        meta_types = ["flavour_id"]
        self._get_property(properties, metadata, ptype, meta_types)

        logger.debug("vnf:%s", vnf)

        return vnf

    def get_all_vl(self, nodeTemplates, node_types):
        vls = []
        for node in nodeTemplates:
            if self.model.isNodeTypeX(node, node_types, VNF_VL_TYPE):
                vl = dict()
                vl['vl_id'] = node['name']
                vl['description'] = node['description']
                vl['properties'] = node['properties']
                vlp = vl['properties']
                nodep = node['properties']
                vlp['connectivity_type']['layer_protocol'] = nodep['connectivity_type']['layer_protocols'][0]
                vlp['vl_profile']['max_bit_rate_requirements'] = nodep['vl_profile']['max_bitrate_requirements']
                vlp['vl_profile']['min_bit_rate_requirements'] = nodep['vl_profile']['min_bitrate_requirements']
                if 'virtual_link_protocol_data' in nodep['vl_profile']:
                    protocol_data = nodep['vl_profile']['virtual_link_protocol_data'][0]
                    vlp['vl_profile']['associated_layer_protocol'] = protocol_data['associated_layer_protocol']
                    if 'l3_protocol_data' in protocol_data:
                        l3 = protocol_data['l3_protocol_data']
                        vlp['vl_profile']['networkName'] = l3.get("name", "")
                        vlp['vl_profile']['cidr'] = l3.get("cidr", "")
                        vlp['vl_profile']['dhcpEnabled'] = l3.get("dhcp_enabled", "")
                        vlp['vl_profile']['ip_version'] = l3.get("ip_version", "")
                    if 'l2_protocol_data' in protocol_data:
                        l2 = protocol_data['l2_protocol_data']
                        vlp['vl_profile']['physicalNetwork'] = l2.get("physical_network", "")
                vls.append(vl)
        return vls

    def get_all_cp(self, nodeTemplates, node_types):
        cps = []
        for node in nodeTemplates:
            if self.model.isNodeTypeX(node, node_types, VDU_CP_TYPE):
                cp = {}
                cp['cp_id'] = node['name']
                cp['cpd_id'] = node['name']
                cp['description'] = node['description']
                cp['properties'] = {}
                nodep = node['properties']
                cp['properties']['trunk_mode'] = nodep.get("trunk_mode", "")
                cp['properties']['layer_protocol'] = nodep.get("layer_protocols", "")
                if 'vnic_type' in nodep:
                    cp['properties']['vnic_type'] = nodep.get("vnic_type", "normal")
                if 'virtual_network_interface_requirements' in nodep:
                    cp['properties']['virtual_network_interface_requirements'] = nodep.get("virtual_network_interface_requirements", "")
                if "protocol" in nodep:
                    node_protocol = nodep['protocol'][0]
                    cp['properties']['protocol_data'] = nodep['protocol']
                    cp_protocol = cp['properties']['protocol_data'][0]
                    cp_protocol['asscociated_layer_protocol'] = node_protocol['associated_layer_protocol']
                    if "address_data" in node_protocol:
                        cp_protocol['address_data'] = node_protocol['address_data'][0]

                cp['vl_id'] = self._get_node_vl_id(node)
                cp['vdu_id'] = self._get_node_vdu_id(node)
                vls = self._buil_cp_vls(node)
                if len(vls) > 1:
                    cp['vls'] = vls
                cps.append(cp)
        return cps

    def get_all_volume_storage(self, nodeTemplates, node_types):
        rets = []
        for node in nodeTemplates:
            if self.model.isNodeTypeX(node, node_types, VDU_STORAGE_TYPE):
                ret = {}
                ret['volume_storage_id'] = node['name']
                if 'description' in node:
                    ret['description'] = node['description']
                ret['properties'] = node['properties']
                rets.append(ret)
        return rets

    def get_all_vdu(self, nodeTemplates, node_types):
        rets = []
        inject_files = []
        for node in nodeTemplates:
            logger.debug("nodeTemplates :%s", node)
            if self.model.isNodeTypeX(node, node_types, VDU_COMPUTE_TYPE):
                ret = {}
                ret['vdu_id'] = node['name']
                ret['type'] = node['nodeType']
                if 'description' in node:
                    ret['description'] = node['description']
                ret['properties'] = node['properties']
                if 'boot_data' in node['properties']:
                    ret['properties']['user_data'] = node['properties']['boot_data']
                    del ret['properties']['boot_data']
                if 'inject_files' in node['properties']:
                    inject_files = node['properties']['inject_files']
                if inject_files is not None:
                    if isinstance(inject_files, list):
                        for inject_file in inject_files:
                            source_path = os.path.join(self.model.basepath, inject_file['source_path'])
                            with open(source_path, "rb") as f:
                                source_data = f.read()
                                source_data_base64 = base64.b64encode(source_data)
                                inject_file["source_data_base64"] = source_data_base64.decode()
                    if isinstance(inject_files, dict):
                        source_path = os.path.join(self.model.basepath, inject_files['source_path'])
                        with open(source_path, "rb") as f:
                            source_data = f.read()
                            source_data_base64 = base64.b64encode(source_data)
                            inject_files["source_data_base64"] = source_data_base64.decode()
                ret['dependencies'] = [self.model.get_requirement_node_name(x) for x in self.model.getNodeDependencys(node)]
                virtual_compute = self.model.getCapabilityByName(node, 'virtual_compute')
                if virtual_compute is not None and 'properties' in virtual_compute:
                    vc = {}
                    vc['virtual_cpu'] = virtual_compute['properties']['virtual_cpu']
                    vc['virtual_memory'] = virtual_compute['properties']['virtual_memory']
                    vc['virtual_storages'] = virtual_compute['properties'].get("virtual_local_storage", {})
                    ret['virtual_compute'] = vc
                ret['vls'] = self._get_linked_vl_ids(node, nodeTemplates)
                ret['cps'] = self._get_virtal_binding_cp_ids(node, nodeTemplates)
                ret['artifacts'] = self.model.build_artifacts(node)
                rets.append(ret)
        logger.debug("rets:%s", rets)
        return rets

    def get_all_endpoint_exposed(self):
        if self.model.vnf:
            external_cps = self._get_external_cps(self.model.vnf.get('requirements', None))
            forward_cps = self._get_forward_cps(self.model.vnf.get('capabilities', None))
            return {"external_cps": external_cps, "forward_cps": forward_cps}
        return {}

    def _get_property(self, properties, metadata, ptype, meta_types):
        if ptype not in properties or properties[ptype] == "":
            for mtype in meta_types:
                data = metadata.get(mtype, "")
                if data != "":
                    properties[ptype] = data

    def _trans_virtual_storage(self, virtual_storage):
        if isinstance(virtual_storage, str):
            return {"virtual_storage_id": virtual_storage}
        else:
            ret = {}
            ret['virtual_storage_id'] = self.model.get_requirement_node_name(virtual_storage)
            return ret

    def _get_linked_vl_ids(self, node, node_templates):
        vl_ids = []
        cps = self._get_virtal_binding_cps(node, node_templates)
        for cp in cps:
            vl_reqs = self.model.getRequirementByName(cp, 'virtual_link')
            for vl_req in vl_reqs:
                vl_ids.append(self.model.get_requirement_node_name(vl_req))
        return vl_ids

    def _get_virtal_binding_cp_ids(self, node, nodeTemplates):
        return [x['name'] for x in self._get_virtal_binding_cps(node, nodeTemplates)]

    def _get_virtal_binding_cps(self, node, nodeTemplates):
        cps = []
        for tmpnode in nodeTemplates:
            if 'requirements' in tmpnode:
                for item in tmpnode['requirements']:
                    for key, value in list(item.items()):
                        if key.upper().startswith('VIRTUAL_BINDING'):
                            req_node_name = self.model.get_requirement_node_name(value)
                            if req_node_name is not None and req_node_name == node['name']:
                                cps.append(tmpnode)
        return cps

    def _get_node_vdu_id(self, node):
        vdu_ids = [self.model.get_requirement_node_name(x) for x in self.model.getRequirementByName(node, 'virtual_binding')]
        if len(vdu_ids) > 0:
            return vdu_ids[0]
        return ""

    def _get_node_vl_id(self, node):
        vl_ids = [self.model.get_requirement_node_name(x) for x in self.model.getRequirementByName(node, 'virtual_link')]
        if len(vl_ids) > 0:
            return vl_ids[0]
        return ""

    def _buil_cp_vls(self, node):
        return [self._build_cp_vl(x) for x in self.model.getRequirementByName(node, 'virtual_link')]

    def _build_cp_vl(self, req):
        cp_vl = {}
        cp_vl['vl_id'] = self.model.get_prop_from_obj(req, 'node')
        relationship = self.model.get_prop_from_obj(req, 'relationship')
        if relationship is not None:
            properties = self.model.get_prop_from_obj(relationship, 'properties')
            if properties is not None and isinstance(properties, dict):
                for key, value in list(properties.items()):
                    cp_vl[key] = value
        return cp_vl

    def _get_external_cps(self, vnf_requirements):
        external_cps = []
        if vnf_requirements:
            if isinstance(vnf_requirements, dict):
                for key, value in list(vnf_requirements.items()):
                    if isinstance(value, list) and len(value) > 0:
                        external_cps.append({"key_name": key, "cpd_id": value[0]})
                    else:
                        external_cps.append({"key_name": key, "cpd_id": value})
            elif isinstance(vnf_requirements, list):
                for vnf_requirement in vnf_requirements:
                    for key, value in list(vnf_requirement.items()):
                        if isinstance(value, list) and len(value) > 0:
                            external_cps.append({"key_name": key, "cpd_id": value[0]})
                        else:
                            external_cps.append({"key_name": key, "cpd_id": value})
        return external_cps

    def _get_forward_cps(self, vnf_capabilities):
        forward_cps = []
        if vnf_capabilities:
            for key, value in list(vnf_capabilities.items()):
                if isinstance(value, list) and len(value) > 0:
                    forward_cps.append({"key_name": key, "cpd_id": value[0]})
                else:
                    forward_cps.append({"key_name": key, "cpd_id": value})
        return forward_cps
