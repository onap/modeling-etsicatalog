# Copyright 2017 ZTE Corporation.
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
import os
import sys
import threading
import traceback
import zipfile

from catalog.packages.biz.vnf_package import VnfPackage
from catalog.packages import const
from catalog.pub.config.config import CATALOG_ROOT_PATH, CATALOG_URL_PATH
from catalog.pub.config.config import REG_TO_MSB_REG_PARAM
from catalog.pub.database.models import VnfPackageModel
from catalog.pub.exceptions import CatalogException, PackageHasExistsException
from catalog.pub.msapi import sdc
from catalog.pub.utils import fileutil
from catalog.pub.utils import toscaparser
from catalog.pub.utils.jobutil import JobUtil, JOB_ERROR_CODE
from catalog.packages.biz.notificationsutil import PkgNotifications

logger = logging.getLogger(__name__)

JOB_ERROR = 255


def nf_get_csars():
    """
    Get NF packages
    :return:
    """
    ret = None
    try:
        ret = NfPackage().get_csars()
    except CatalogException as e:
        return [1, e.args[0]]
    except Exception as e:
        logger.error(e.args[0])
        logger.error(traceback.format_exc())
        return [1, str(sys.exc_info())]
    return ret


def nf_get_csar(csar_id):
    """
    Get NF package by id
    :param csar_id:
    :return:
    """
    ret = None
    try:
        ret = NfPackage().get_csar(csar_id)
    except CatalogException as e:
        return [1, e.args[0]]
    except Exception as e:
        logger.error(e.args[0])
        logger.error(traceback.format_exc())
        return [1, str(sys.exc_info())]
    return ret


def parse_vnfd(csar_id, inputs):
    """
    Parse VNFD
    :param csar_id:
    :param inputs:
    :return:
    """
    ret = None
    try:
        nf_pkg = VnfPackageModel.objects.filter(vnfPackageId=csar_id)
        if not nf_pkg:
            raise CatalogException("VNF CSAR(%s) does not exist." % csar_id)
        csar_path = nf_pkg[0].localFilePath
        ret = {"model": toscaparser.parse_vnfd(csar_path, inputs)}
    except CatalogException as e:
        return [1, e.args[0]]
    except Exception as e:
        logger.error(e.args[0])
        logger.error(traceback.format_exc())
        return [1, str(sys.exc_info())]
    return [0, ret]


class NfDistributeThread(threading.Thread):
    """
    Sdc NF Package Distribute
    """

    def __init__(self, csar_id, vim_ids, lab_vim_id, job_id):
        threading.Thread.__init__(self)
        self.csar_id = csar_id
        self.vim_ids = vim_ids
        self.lab_vim_id = lab_vim_id
        self.job_id = job_id

        self.csar_save_path = os.path.join(CATALOG_ROOT_PATH, csar_id)

    def run(self):
        try:
            self.on_distribute()
        except PackageHasExistsException as e:
            self.rollback_distribute()
            JobUtil.add_job_status(self.job_id, JOB_ERROR, e.args[0], error_code=JOB_ERROR_CODE.PACKAGE_EXIST)
        except CatalogException as e:
            self.rollback_distribute()
            JobUtil.add_job_status(self.job_id, JOB_ERROR, e.args[0], error_code=JOB_ERROR_CODE.CATALOG_EXCEPTION)
        except Exception as e:
            logger.error(e.args[0])
            logger.error(traceback.format_exc())
            logger.error(str(sys.exc_info()))
            self.rollback_distribute()
            JobUtil.add_job_status(self.job_id, JOB_ERROR, "Failed to distribute CSAR(%s)" % self.csar_id,
                                   error_code=JOB_ERROR_CODE.SYSTEM_ERROR)

    def on_distribute(self):
        JobUtil.create_job(
            inst_type='nf',
            jobaction='on_distribute',
            inst_id=self.csar_id,
            job_id=self.job_id)
        JobUtil.add_job_status(self.job_id, 5, "Start CSAR(%s) distribute." % self.csar_id)

        if VnfPackageModel.objects.filter(vnfPackageId=self.csar_id):
            err_msg = "NF CSAR(%s) already exists." % self.csar_id
            JobUtil.add_job_status(self.job_id, JOB_ERROR, err_msg, error_code=JOB_ERROR_CODE.PACKAGE_EXIST)
            return

        artifact = sdc.get_artifact(sdc.ASSETTYPE_RESOURCES, self.csar_id)
        local_path = os.path.join(CATALOG_ROOT_PATH, self.csar_id)
        csar_name = "%s.csar" % artifact.get("name", self.csar_id)
        local_file_name = sdc.download_artifacts(artifact["toscaModelURL"], local_path, csar_name)
        if local_file_name.endswith(".csar") or local_file_name.endswith(".zip"):
            fileutil.unzip_csar(local_file_name, local_path)
            vendor_vnf_file = ''
            # find original vendor ETSI package under the ETSI_PACKAGE directory
            etsi_package_dir = os.path.join(local_path, "Artifacts/Deployment/ETSI_PACKAGE")
            if os.path.exists(etsi_package_dir):
                files = os.listdir(etsi_package_dir)
                for file_name in files:
                    a_file = os.path.join(etsi_package_dir, file_name)
                    if os.path.isfile(a_file) & file_name.endswith(".csar"):
                        vendor_vnf_file = a_file
                        break

            # find original vendor ETSI package under Artifacts/Deployment/OTHER directory
            if vendor_vnf_file.strip() == '':
                vendor_vnf_file = os.path.join(local_path, "Artifacts/Deployment/OTHER/vnf.csar")
                if os.path.exists(vendor_vnf_file):
                    local_file_name = vendor_vnf_file
            else:
                local_file_name = vendor_vnf_file

        # create VNFD zip file
        self.create_vnfd_zip(self.csar_id, vendor_vnf_file)

        vnfd_json = toscaparser.parse_vnfd(local_file_name)
        vnfd = json.JSONDecoder().decode(vnfd_json)

        if not vnfd.get("vnf"):
            raise CatalogException("VNF properties and metadata in VNF Package(id=%s) are empty." % self.csar_id)

        vnfd_id = vnfd["vnf"]["properties"].get("descriptor_id", "")
        if VnfPackageModel.objects.filter(vnfdId=vnfd_id):
            logger.error("VNF package(%s) already exists.", vnfd_id)
            raise PackageHasExistsException("VNF package(%s) already exists." % vnfd_id)
        JobUtil.add_job_status(self.job_id, 30, "Save CSAR(%s) to database." % self.csar_id)
        vnfd_ver = vnfd["vnf"]["properties"].get("descriptor_version", "")
        vnf_provider = vnfd["vnf"]["properties"].get("provider", "")
        vnf_software_version = vnfd["vnf"]["properties"].get("software_version", "")
        vnfd_product_name = vnfd["vnf"]["properties"].get("product_name", "")
        # Update VNF package Model to DB
        VnfPackageModel(
            vnfPackageId=self.csar_id,
            vnfdId=vnfd_id,
            vnfVendor=vnf_provider,
            vnfdProductName=vnfd_product_name,
            vnfdVersion=vnfd_ver,
            vnfSoftwareVersion=vnf_software_version,
            vnfdModel=vnfd_json,
            localFilePath=local_file_name,
            vnfPackageUri=csar_name,
            onboardingState=const.PKG_STATUS.ONBOARDED,
            operationalState=const.PKG_STATUS.ENABLED,
            usageState=const.PKG_STATUS.NOT_IN_USE
        ).save()
        JobUtil.add_job_status(self.job_id, 100, "CSAR(%s) distribute successfully." % self.csar_id)
        send_notification(self.csar_id, const.PKG_NOTIFICATION_TYPE.ONBOARDING,
                          const.PKG_CHANGE_TYPE.OP_STATE_CHANGE)

    def create_vnfd_zip(self, csar_id, vendor_vnf_file):
        """
        Create VNFD zip file.
        :param csar_id: CSAR Id
        :param vendor_vnf_file: the vendor original package(csar)
        :return:
        """
        if os.path.exists(vendor_vnf_file):
            # create VNFD from vendor original package
            VnfPackage().creat_vnfd(csar_id, vendor_vnf_file)
        else:
            try:
                vnf_package_path = os.path.join(CATALOG_ROOT_PATH, self.csar_id)
                vnfd_zip_file = os.path.join(vnf_package_path, 'VNFD.zip')
                with zipfile.ZipFile(vnfd_zip_file, 'w', zipfile.ZIP_DEFLATED) as vnfd_zip:
                    def_path = os.path.join(vnf_package_path, "Definitions")
                    if os.path.exists(def_path):
                        def_files = os.listdir(def_path)
                        for def_file in def_files:
                            full_path = os.path.join(def_path, def_file)
                            vnfd_zip.write(full_path, def_file)
            except Exception as e:
                logger.error(e)
                if os.path.exists(vnfd_zip_file):
                    os.remove(vnfd_zip_file)

    def rollback_distribute(self):
        try:
            VnfPackageModel.objects.filter(vnfPackageId=self.csar_id).delete()
            fileutil.delete_dirs(self.csar_save_path)
        except Exception as e:
            logger.error(e.args[0])
            logger.error(traceback.format_exc())
            logger.error(str(sys.exc_info()))


class NfPkgDeleteThread(threading.Thread):
    """
    Sdc NF Package Deleting
    """

    def __init__(self, csar_id, job_id):
        threading.Thread.__init__(self)
        self.csar_id = csar_id
        self.job_id = job_id

    def run(self):
        try:
            self.delete_csar()
        except CatalogException as e:
            JobUtil.add_job_status(self.job_id, JOB_ERROR, e.args[0])
        except Exception as e:
            logger.error(e.args[0])
            logger.error(traceback.format_exc())
            logger.error(str(sys.exc_info()))
            JobUtil.add_job_status(self.job_id, JOB_ERROR, "Failed to delete CSAR(%s)" % self.csar_id)

    def delete_csar(self):
        JobUtil.create_job(
            inst_type='nf',
            jobaction='delete',
            inst_id=self.csar_id,
            job_id=self.job_id)
        JobUtil.add_job_status(self.job_id, 5, "Start to delete CSAR(%s)." % self.csar_id)
        send_notification(self.csar_id, const.PKG_NOTIFICATION_TYPE.CHANGE,
                          const.PKG_CHANGE_TYPE.PKG_DELETE)
        VnfPackageModel.objects.filter(vnfPackageId=self.csar_id).delete()

        JobUtil.add_job_status(self.job_id, 50, "Delete local CSAR(%s) file." % self.csar_id)

        csar_save_path = os.path.join(CATALOG_ROOT_PATH, self.csar_id)
        fileutil.delete_dirs(csar_save_path)

        JobUtil.add_job_status(self.job_id, 100, "Delete CSAR(%s) successfully." % self.csar_id)


class NfPackage(object):
    """
    Actions for sdc nf package.
    """

    def __init__(self):
        pass

    def get_csars(self):
        csars = []
        nf_pkgs = VnfPackageModel.objects.filter()
        for nf_pkg in nf_pkgs:
            ret = self.get_csar(nf_pkg.vnfPackageId)
            csars.append(ret[1])
        return [0, csars]

    def get_csar(self, csar_id):
        pkg_info = {}
        nf_pkg = VnfPackageModel.objects.filter(vnfPackageId=csar_id)
        if not nf_pkg:
            nf_pkg = VnfPackageModel.objects.filter(vnfdId=csar_id)

        if nf_pkg:
            db_csar_id = nf_pkg[0].vnfPackageId
            pkg_info["vnfdId"] = nf_pkg[0].vnfdId
            pkg_info["vnfPackageId"] = nf_pkg[0].vnfPackageId
            pkg_info["vnfdProvider"] = nf_pkg[0].vnfVendor
            pkg_info["vnfdVersion"] = nf_pkg[0].vnfdVersion
            pkg_info["vnfVersion"] = nf_pkg[0].vnfSoftwareVersion
            pkg_info["csarName"] = nf_pkg[0].vnfPackageUri
            pkg_info["vnfdModel"] = nf_pkg[0].vnfdModel
            pkg_info["downloadUrl"] = "http://%s:%s/%s/%s/%s" % (
                REG_TO_MSB_REG_PARAM[0]["nodes"][0]["ip"],
                REG_TO_MSB_REG_PARAM[0]["nodes"][0]["port"],
                CATALOG_URL_PATH,
                db_csar_id,
                nf_pkg[0].vnfPackageUri)
        else:
            raise CatalogException("Vnf package[%s] not Found." % csar_id)

        csar_info = {
            "csarId": db_csar_id,
            "packageInfo": pkg_info,
            "imageInfo": []
        }
        return [0, csar_info]


def send_notification(pkg_id, type, pkg_change_type, operational_state=None):
    notify = PkgNotifications(type, pkg_id, change_type=pkg_change_type,
                              operational_state=operational_state)
    notify.send_notification()
