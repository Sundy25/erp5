##############################################################################
#
# Copyright (c) 2004 Nexedi SARL and Contributors. All Rights Reserved.
#          Aurelien Calonne <aurel@nexedi.com>
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
##############################################################################

#
# Skeleton ZopeTestCase
#

from random import randint

import os, sys
if __name__ == '__main__':
  execfile(os.path.join(sys.path[0], 'framework.py'))

# Needed in order to have a log file inside the current folder
os.environ['EVENT_LOG_FILE'] = os.path.join(os.getcwd(), 'zLOG.log')
os.environ['EVENT_LOG_SEVERITY'] = '-300'

from Testing import ZopeTestCase
from Products.ERP5Type.tests.ERP5TypeTestCase import ERP5TypeTestCase
from AccessControl.SecurityManagement import newSecurityManager, noSecurityManager
from zLOG import LOG
from App.config import getConfiguration
from Products.ERP5Type.tests.Sequence import Sequence, SequenceList

class TestTrashTool(ERP5TypeTestCase):
  """
  Test some fonctionnality
  """
  run_all_test = 1
  
  def getTitle(self):
    return "Trash Tool"

  def enableActivityTool(self):
    """
    You can override this.
    Return if we should create (1) or not (0) an activity tool.
    """
    return 1

  def afterSetUp(self):
    self.login()
    portal = self.getPortal()
    catalog_tool = self.getCatalogTool()

  def login(self):
    uf = self.getPortal().acl_users
    uf._doAddUser('seb', '', ['Manager'], [])
    user = uf.getUserById('seb').__of__(uf)
    newSecurityManager(None, user)

  def stepTic(self,**kw):
    self.tic()

  def stepAddBaseCategory(self, sequence=None, sequence_list=None, **kw):
    """
    Add a BaseCategory
    """
    pc = self.getCategoryTool()
    base_category = pc.newContent(portal_type = 'Base Category')
    self.failUnless(base_category is not None)
    sequence.edit(bc_id=base_category.getId())

  def stepAddCategories(self, sequence=None, sequence_list=None, **kw):
    """
    Add category to a base category
    """
    bc_id = sequence.get('bc_id')
    pc = self.getCategoryTool()
    base_category = pc._getOb(bc_id, None)    
    self.failUnless(base_category is not None)
    category_list = []
    for i in xrange(10):
      category = base_category.newContent(portal_type='Category')
      self.failUnless(category is not None)
      category_list.append(category.getId())
    sequence.edit(category_id_list=category_list)

  def stepCheckTrashToolExists(self, sequence=None, sequence_list=None, **kw):
    """
    Check existence of trash tool
    """
    self.failUnless(self.getTrashTool() is not None)

  def stepCreateTrashBin(self, sequence=None, sequence_list=None, **kw):
    """
    Create a trash bin
    """
    trash = self.getTrashTool()
    pt = self.getTemplateTool()
    bt_id = 'fake_id'
    n = 0
    while bt_id in pt.objectIds():
      n = n + 1
      bt_id = 'fake_id_%s' %(n)      
    bt = pt.newContent(id=bt_id, portal_type="Business Template")
    self.failUnless(bt is not None)
    trashbin = trash.newTrashBin(bt_title='fake_bin', bt=bt)
    self.failUnless(trashbin is not None)
    self.failUnless('fake_bin' in trashbin.getId())
    sequence.edit(trash_id=trashbin.getId())

  def stepCheckTrashBinIndexable(self, sequence=None, sequence_list=None, **kw ):
    """
    Check trash bin is indexable
    """
    trash_id = sequence.get('trash_id')
    trash = self.getTrashTool()
    trashbin = trash._getOb(trash_id, None)
    self.failUnless(trashbin is not None)
    self.failUnless(trashbin.isIndexable)

  def stepCheckObjectNotBackup(self, sequence=None, sequence_list=None, **kw):
    """
    Check that base category has not been backup
    """
    trash_id = sequence.get('trash_id')
    trash = self.getTrashTool()
    trashbin = trash._getOb(trash_id, None)
    self.failUnless(trashbin is not None)
    self.assertEqual(len(list(trashbin.objectIds())), 0)

  def stepCheckObjectBackupWithoutSubObjects(self, sequence=None, sequence_list=None, **kw):
    """
    Check that base category has not been backup
    """
    trash_id = sequence.get('trash_id')
    trash = self.getTrashTool()
    trashbin = trash._getOb(trash_id, None)
    self.failUnless(trashbin is not None)
    trashbin_objects_list = list(trashbin.objectValues())
    self.failUnless(len(trashbin_objects_list) > 0)
    self.assertEqual(len(trashbin_objects_list), 1)
    # get portal_catogories trash folder
    obj = trashbin_objects_list[0]
    self.assertEqual(obj.getId(), 'portal_categories_items')
    self.assertEqual(obj.getPortalType(), 'Trash Folder')
    #    self.assertEqual(obj.isIndexable, 0)
    # get backup base category
    cat_objects_list = list(obj.objectValues())
    self.assertEqual(len(cat_objects_list), 1)
    cat_object = cat_objects_list[0]
    bc_id = sequence.get('bc_id')
    self.assertEqual(cat_object.getId(), bc_id)
    self.assertEqual(cat_object.isIndexable, 0)
    self.assertEqual(cat_object.getPortalType(), 'Base Category')
    # check no subobjects
    subcat_objects_list = (cat_object.objectIds())
    self.assertEqual(len(subcat_objects_list), 0)    

  def stepCheckObjectBackupWithSubObjects(self, sequence=None, sequence_list=None, **kw):
    """
    Check that base category has not been backup
    """
    trash_id = sequence.get('trash_id')
    trash = self.getTrashTool()
    trashbin = trash._getOb(trash_id, None)
    self.failUnless(trashbin is not None)
    # get category trash folder
    bc_id = sequence.get('bc_id')
    trashbin_objects_list = list(trashbin.objectValues())
    self.failUnless(len(trashbin_objects_list) > 0)
    self.assertEqual(len(trashbin_objects_list), 1)
    object = trashbin_objects_list[0]
    self.assertEqual(object.getId(), 'portal_categories_items')    
    self.assertEqual(object.getPortalType(), 'Trash Folder')
    #    self.assertEqual(obj.isIndexable, 0)
    # get base category backup
    cat_objects_list = list(object.objectValues())
    self.assertEqual(len(cat_objects_list), 1)
    cat_object = cat_objects_list[0]
    bc_id = sequence.get('bc_id')
    self.assertEqual(cat_object.getId(), bc_id)
    self.assertEqual(cat_object.isIndexable, 0)
    self.assertEqual(cat_object.getPortalType(), 'Base Category')
    # check subobject list
    subcat_objects_list = (cat_object.objectIds())
    self.assertNotEqual(len(subcat_objects_list), 0)
    categ_id_list = sequence.get('category_id_list')
    for id in subcat_objects_list:
      self.failUnless(id in categ_id_list)
      cat = cat_object._getOb(id, None)
      self.failUnless(cat is not None)
      self.failUnless(cat.isIndexable, 0)
      self.assertEqual(cat.getPortalType(), 'Category')

  def stepBackupObjectsWithSave(self, sequence=None, sequence_list=None, **kw):
    """
    Backup objects and check subobjects are return
    """
    trash_id = sequence.get('trash_id')
    trash = self.getTrashTool()
    trashbin = trash._getOb(trash_id, None)
    # get base category to backup
    bc_id = sequence.get('bc_id')
    pc = self.getCategoryTool()
    base_category = pc._getOb(bc_id, None)
    self.failUnless(base_category is not None)
    subobjects_ids = base_category.objectIds()
    bc_path = base_category.getPath().split('/')[2:-1]
    # check backup
    backup_subobjects_ids = trash.backupObject(trashbin, bc_path, bc_id, save=1)
    self.failUnless(backup_subobjects_ids.keys().sort() == list(subobjects_ids).sort())

  def stepBackupObjectsWithoutSave(self, sequence=None, sequence_list=None, **kw):
    """
    Backup objects and check subobjects are return
    """
    trash_id = sequence.get('trash_id')
    trash = self.getTrashTool()
    trashbin = trash._getOb(trash_id, None)
    # get base category to backup
    bc_id = sequence.get('bc_id')
    pc = self.getCategoryTool()
    base_category = pc._getOb(bc_id, None)
    self.failUnless(base_category is not None)
    subobjects_ids = base_category.objectIds()
    bc_path = base_category.getPath().split('/')[1:-1]
    # check backup
    backup_subobjects_ids = trash.backupObject(trashbin, bc_path, bc_id, save=0)
    self.failUnless(backup_subobjects_ids.keys().sort() == list(subobjects_ids).sort())

  def stepBackupObjectsWithKeepingSubobjects(self, sequence=None, sequence_list=None, **kw):
    """
    Backup objects and check subobjects are return
    """
    trash_id = sequence.get('trash_id')
    trash = self.getTrashTool()
    trashbin = trash._getOb(trash_id, None)
    # get base category to backup
    bc_id = sequence.get('bc_id')
    pc = self.getCategoryTool()
    base_category = pc._getOb(bc_id, None)
    self.failUnless(base_category is not None)
    subobjects_ids = base_category.objectIds()
    bc_path = base_category.getPath().split('/')[2:-1]
    LOG('bc_path', 0, bc_path)
    # check backup
    backup_subobjects_ids = trash.backupObject(trashbin, bc_path, bc_id, save=1, keep_subobjects=1)
    # no subobjects return
    self.assertEqual(len(backup_subobjects_ids), 0)
    
  # tests
  def test_01_checkTrashBinCreation(self, quiet=0, run=run_all_test):
    if not run: return
    if not quiet:
      message = 'Test Check TrashBin Creation'
      ZopeTestCase._print('\n%s ' % message)
      LOG('Testing... ', 0, message)
    sequence_list = SequenceList()
    sequence_string = '\
                       CheckTrashToolExists  \
                       CreateTrashBin \
                       CheckTrashBinIndexable \
                       '
    sequence_list.addSequenceString(sequence_string)
    sequence_list.play(self)    
    
  def test_02_checkBackupWithoutSave(self, quiet=0, run=run_all_test):
    if not run: return
    if not quiet:
      message = 'Test Check Backup Without Save'
      ZopeTestCase._print('\n%s ' % message)
      LOG('Testing... ', 0, message)
    sequence_list = SequenceList()
    sequence_string = '\
                       CheckTrashToolExists  \
                       CreateTrashBin \
                       CheckTrashBinIndexable \
                       AddBaseCategory \
                       AddCategories \
                       Tic \
                       BackupObjectsWithoutSave \
                       CheckObjectNotBackup \
                       '
    sequence_list.addSequenceString(sequence_string)
    sequence_list.play(self)    

  def test_03_checkBackupWithSave(self, quiet=0, run=run_all_test):
    if not run: return
    if not quiet:
      message = 'Test Check Backup With Save'
      ZopeTestCase._print('\n%s ' % message)
      LOG('Testing... ', 0, message)
    sequence_list = SequenceList()
    sequence_string = '\
                       CheckTrashToolExists  \
                       CreateTrashBin \
                       CheckTrashBinIndexable \
                       AddBaseCategory \
                       AddCategories \
                       Tic \
                       BackupObjectsWithSave \
                       Tic \
                       CheckObjectBackupWithoutSubObjects \
                       '
    sequence_list.addSequenceString(sequence_string)
    sequence_list.play(self)    

  def test_04_checkBackupWithSubObjects(self, quiet=0, run=run_all_test):
    if not run: return
    if not quiet:
      message = 'Test Check Backup Without Subobjects'
      ZopeTestCase._print('\n%s ' % message)
      LOG('Testing... ', 0, message)
    sequence_list = SequenceList()
    sequence_string = '\
                       CheckTrashToolExists  \
                       CreateTrashBin \
                       CheckTrashBinIndexable \
                       AddBaseCategory \
                       AddCategories \
                       Tic \
                       BackupObjectsWithKeepingSubobjects \
                       Tic \
                       CheckObjectBackupWithSubObjects \
                       '
    sequence_list.addSequenceString(sequence_string)
    sequence_list.play(self)    

if __name__ == '__main__':
  framework()
else:
  import unittest
  def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestBusinessTemplate))
    return suite
