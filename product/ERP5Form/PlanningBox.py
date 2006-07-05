##############################################################################
#
# Copyright (c) 2005 Nexedi SARL and Contributors. All Rights Reserved.
#                    Tomas Bernard <thomas@nexedi.com>
#     from an original experimental script written by :
#                    Jonathan Loriette <john@nexedi.com>
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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################

    # XXX need to decide how Constraints between task should be defined on
    # planning.
    # ideally, an external method should be called for validating all
    # constraints within the planning. (such a method sould be called from
    # anywhere in the Project module : listbox, editing form).
    # this method should return a list of all the objects' urls that does not
    # fit the constraints.


import pdb

import string, types, sys

# class monitoring access security control
from Products.PythonScripts.Utility import allow_class
from AccessControl import ClassSecurityInfo
from Globals import InitializeClass

from Form import BasicForm
from Products.Formulator.Field import ZMIField
from Products.Formulator.DummyField import fields
from Products.Formulator.MethodField import BoundMethod
from DateTime import DateTime
from Products.Formulator import Widget, Validator
from Products.Formulator.Errors import FormValidationError, ValidationError
from SelectionTool import makeTreeList,TreeListLine
from Selection import Selection, DomainSelection
import OFS
from AccessControl import ClassSecurityInfo
from zLOG import LOG
from copy import copy
from Acquisition import aq_base, aq_inner, aq_parent, aq_self
from Products.Formulator.Form import BasicForm
from Products.CMFCore.utils import getToolByName
from Products.ERP5Type.Utils import getPath
from Products.ERP5Type.Message import Message

class PlanningBoxValidator(Validator.StringBaseValidator):
  """
  Class holding all methods used to validate a modified PlanningBox
  can be called only from an HTML rendering using wz_dragdrop script
  """
  def validate(self,field,key,REQUEST):
    """
    main method to solve validation
    - rebuild the whole planning structure but do not display it.
      this is needed to be able to get the block positions
    - apply block movements recovered from the java script
    - for each block moved, check the modification (over he primary axis in
      case task association has changed, and also over the secondary axis to
      check block movement / resizement).
      Beware : This checking part does not include constraint checking.
    - build a list with the validated blocks and also with the error blocks
      (if any).
    - return a dict of values to update objects in case no errors have been
      found. Otherwise save in the REQUEST the list of error blocks so that
      they can be displayed in a special way.
    """

    # init params
    value = None
    form = field.aq_parent
    here = getattr(form, 'aq_parent', REQUEST)

    # recover usefull properties
    block_moved_string = REQUEST.get('block_moved','')
    block_previous_string = REQUEST.get('previous_block_moved','')

    #pdb.set_trace()

    ##################################################
    ############## REBUILD STRUCTURE #################
    ##################################################
    # build structure
    structure = PlanningBoxWidgetInstance.render_structure(field=field,
                         key=key, value=value, REQUEST=REQUEST, here=here)

    # getting coordinates script generator
    planning_coordinates_method = getattr(here,'planning_coordinates')
    # calling script to generate coordinates
    planning_coordinates = planning_coordinates_method(structure=structure)

    ##################################################
    ########## RECOVERING BLOCK MOVED DICTS ##########
    ##################################################
    #  converting string to a structure
    block_moved_list = self.getBlockPositionFromString(block_moved_string)
    # block_moved_list now holds a list of structure recovered from the REQUEST
    # and correspondig to the movements done before validating
    block_previous_list =\
                       self.getBlockPositionFromString(block_previous_string)
    # list of previous blocks moved if an error occured during previous
    # validation

    # updating block_moved_list using block_previous_list.
    # This is very important not to escape processing blocks that have been
    # moved during a previous validation attempt.
    if block_previous_list != [] and block_moved_list != []:
      for block_previous in block_previous_list:
        # checking if the block has been moved again in this validation attempt
        # if it is the case, the block must be also present in the current
        # block_moved_list
        block_found = {}
        for block_moved in block_moved_list:
          if block_moved['name'] == block_previous['name']:
            block_found = block_moved
            break
        if block_found != {}:
          # block has been moved again, updating its properties in the current
          # list to take into account its previous position. current block is
          # known as 'block_found', and the value to update is the original
          # absolute position used to get relative coordinates
          block_found['old_X'] = block_previous['old_X']
          block_found['old_Y'] = block_previous['old_Y']
        else:
          # block has not been moved again, adding old block informations to
          # the current list of block_moved
          block_moved_list.append(block_previous)
    elif block_previous_list != []:
      # block_moved_list is empty but not block_previous_list. This means the
      # user is trying to validate again without any change
      block_moved_list = block_previous_list
    elif block_moved_list != []:
      # block_previous_list is empty, this means this is the first validation
      # attempt. Using the block_moved_list as it is
      pass
    else:
      # the two lists are empty : nothing to validate
      return None
    # block_moved_list is updated


    # dict aimed to hold all informations about block
    final_block_dict = {}
    # dict holding all the activities that will need an update because at least
    # one of the blocks concerned is moved
    activity_dict = {}
    # list holding all the activities having one of their block not validated
    # in such a case the update process of the activity is canceled
    warning_activity_list = []
    error_block_list = []
    error_info_dict = {}


    ##################################################
    ########## GETTING BLOCK INFORMATIONS ############
    ##################################################
    # iterating each block_moved element and recovering all usefull properties
    # BEWARE : no update is done here as an activity can be composed of several
    # blocks and so we need first to check all the blocks moved
    for block_moved in block_moved_list:
      final_block = {}
      # recovering the block object from block_moved informations
      final_block['block_object'] = self.getBlockObject(block_moved['name'], \
                                                   structure.planning.content)
      # recovering original activity object
      final_block['activity_origin'] = \
           final_block['block_object'].parent_activity
      # recovering original axis_group object
      final_block['group_origin'] = \
           final_block['activity_origin'].parent_axis_element.parent_axis_group
      # recovering relative block information in planning_coordinates
      final_block['block_info'] = \
           planning_coordinates['content'][block_moved['name']]

      # calculating delta
      # block_moved holds coordinates recovered from drag&drop script, while
      # block_info has the relative coordinates.
      # In fact the Drag&Drop java script used to get destination coordinates
      # gives them in absolute. so using original block position to get the
      # relative position
      deltaX = block_moved['old_X'] - final_block['block_info']['margin-left']
      deltaY = block_moved['old_Y'] - final_block['block_info']['margin-top']

      # calculating new block position:
      # width and height are already in the good format
      block_moved['left'] = block_moved['new_X'] - deltaX
      block_moved['top']  = block_moved['new_Y'] - deltaY

      # abstracting axis representation (for generic processing)
      if structure.planning.calendar_view == 0:
        block_moved['main_axis_position']      = block_moved['top']
        block_moved['main_axis_length']        = block_moved['height']
        block_moved['secondary_axis_position'] = block_moved['left']
        block_moved['secondary_axis_length']   = block_moved['width']
        # used afterwards to get destination group
        group_position = 'margin-top'
        group_length = 'height'
        # used afterwards to get secondary axis displacements and modifications
        axis_length = 'width'
      else:
        block_moved['main_axis_position']      = block_moved['left']
        block_moved['main_axis_length']        = block_moved['width']
        block_moved['secondary_axis_position'] = block_moved['top']
        block_moved['secondary_axis_length']   = block_moved['height']
        group_position = 'margin-left'
        group_length = 'width'
        axis_length = 'height'

      # calculating center of block over main axis to check block position
      block_moved['center'] = (block_moved['main_axis_length'] / 2) + \
                               block_moved['main_axis_position']

      # now that block coordinates are recovered as well as planning
      # coordinates, recovering destination group over the main axis to know
      # if the block has been moved from a group to another
      #pdb.set_trace()
      group_destination = self.getDestinationGroup(structure,
               block_moved,planning_coordinates['main_axis'],
               group_position, group_length)

      if group_destination == None:
        # !! Generate an Error !!
        # block has been moved outside the content area (not in line with any
        # group of the current area).
        # adding current block to error_list
        error_block_list.append(block_moved['name'])
        error_info_dict[block_moved['name']] = 'out of bounds on main axis'
        # adding if necessary current activity to warning_list
        if final_block['activity_origin'].name not in warning_activity_list:
          warning_activity_list.append(final_block['activity_origin'].name)

      else:
        # now that all informations about the main axis changes are
        # known, checking modifications over the secondary axis.
        secondary_axis_positions = self.getDestinationBounds(structure,
                block_moved, final_block['block_object'],
                planning_coordinates, axis_length,
                destination_group = group_destination)
        if secondary_axis_positions[2] == 1 :
          # !! Generate an Error !!
          # block has been moved outside the content area (bounds do not match
          # current area limits)
          if block_moved['name'] not in error_block_list:
            error_block_list.append(block_moved['name'])
            error_info_dict[block_moved['name']] = 'out of bounds on sec axis'
            if final_block['activity_origin'].name not in warning_activity_list:
              warning_activity_list.append(final_block['activity_origin'].name)


      block_moved['secondary_axis_start'] = secondary_axis_positions[0]
      block_moved['secondary_axis_stop'] = secondary_axis_positions[1]

      final_block['block_moved'] = block_moved
      final_block['group_destination'] = group_destination

      #final_block_dict[block_moved['name']] = final_block
      try:
        activity_dict[final_block['activity_origin'].name].append(final_block)
      except KeyError:
        activity_dict[final_block['activity_origin'].name] = [final_block]



    ##################################################
    # getting object_dict to update object properties once activities are up to
    # date. Activities values will be updated directly on the 
    object_dict = self.getObjectDict(structure)

    ##################################################
    ############# UPDATING ACTIVITIES ################
    ##################################################
    # if activity is composed of several blocks, then check if it is needed to
    # update activity itself depending on blocks moved. Beware this part only
    # deals with activities (i.e task object) : an object can be represented by
    # several activities (in case of calendar mode for example).
    # build a dict
    update_list = []
    errors_list = []
    # getting start & stop property names
    start_property = structure.basic.field.get_value('x_start_bloc')
    stop_property = structure.basic.field.get_value('x_stop_bloc')
    # getting round_script if exists
    round_script=getattr(here,field.get_value('round_script'),None)
    # now processing activity updates
    for activity_name in activity_dict.keys():
      # recovering list of moved blocks in the current activity
      activity_block_moved_list = activity_dict[activity_name]
      # recovering activity object from first moved block
      activity_object = activity_block_moved_list[0]['activity_origin']
      # now getting list of blocks related to the activity (moved or not)
      activity_block_list = activity_object.block_list
      if activity_object.name in warning_activity_list:
        # activity contains a block that has not been validated
        # The validation update process is canceled, and the error is reported
        err = ValidationError(StandardError,activity_object)
        errors_list.append(err)
        pass
      else:
        # no error : continue
        # recovering new activity bounds
        (start_value, stop_value) = \
             self.getActivityBounds(activity_object, activity_block_moved_list,
                                    activity_block_list)
        # call specific external method to round value
        if round_script != None:
          start_value = round_script(start_value)
          stop_value = round_script(stop_value)
        # adding object name to list of objects to update
        if activity_object.object.getUrl() not in update_list :
          update_list.append(activity_object.object.getUrl())
        # saving updated informations in the final dict
        for activity_desc in object_dict[activity_object.object.getUrl()] :
          if activity_desc['activity_name'] == activity_object.name:
            activity_desc['axis_start'] = start_value
            activity_desc['axis_stop'] = stop_value


    ##################################################
    ############### UPDATING OBJECTS #################
    ##################################################
    # using result from updated activities to process update on objects.
    update_dict = {}
    # first building a dict with all informations for each object.
    # now processing activity updates
    for object_name in update_list:
      object_info = object_dict[object_name]
      axis_start = None
      axis_stop  = None
      for activity in object_info:
        if activity['activity_name'] == 'update':
          # case current activity is in fact 'fake' activity, just data telling
          # if can update min & max bounds according to global decision toward
          # objects.
          can_update_start = activity['axis_start']
          can_update_stop  = activity['axis_stop']
        else:
          if axis_start > activity['axis_start'] or axis_start == None:
            axis_start = activity['axis_start']
          if axis_stop  < activity['axis_stop']  or axis_stop  == None:
            axis_stop = activity['axis_stop']
      update_dict[object_name] = {}
      if can_update_start and axis_start != None:
        update_dict[object_name][start_property] = axis_start
      if can_update_stop  and axis_stop  != None:
        update_dict[object_name][stop_property]  = axis_stop


    # testing if need to raise errors
    if len(errors_list) > 0:
      # need to raise an error
      # rebuilt position string including new values
      block_moved_string = self.setBlockPositionToString(block_moved_list)
      # save the current block_list for repositionning the blocks
      # to their final position
      REQUEST.set('previous_block_moved',block_moved_string)
      # saving blocks not validated as such as the activity they belong to to
      # apply a special treatment.
      REQUEST.set('warning_activity_list',warning_activity_list)
      REQUEST.set('error_block_list',error_block_list)
      REQUEST.set('error_info_dict',error_info_dict)
      # now raise error => automatically called
      # parameters are :
      # -list of errors
      # - dict with error results
      raise FormValidationError(errors_list, {} )

    # the whole process is now finished, just need to return final dict
    # for updating data
    return update_dict



  def getBlockPositionFromString(self, block_string):
    """
    takes a string with block data and convert it to a list of dicts
    """
    block_list = []
    if block_string != '':
      block_object_list = block_string.split('*')
      for block_object_string in block_object_list:
        block_dict = None
        block_dict = {}
        block_sub_list = block_object_string.split(',')
        block_dict['name'] = block_sub_list[0]
        block_dict['old_X'] = float(block_sub_list[1])
        block_dict['old_Y'] = float(block_sub_list[2])
        block_dict['new_X'] = float(block_sub_list[3])
        block_dict['new_Y'] = float(block_sub_list[4])
        block_dict['width'] = float(block_sub_list[5])
        block_dict['height'] = float(block_sub_list[6])
        block_list.append(block_dict)
      return block_list
    else:
      return block_list

  def setBlockPositionToString(self,block_list):
    """
    takes a list of dicts updated and convert it to a string in order to save
    it in the request
    """
    block_string = ''
    if block_list != []:
      block_object_list = []
      for block_dict in block_list:
        # property position is important that's why ','.join() is not used in
        # this case
        block_sub_string  = '%s,%s,%s,%s,%s,%s,%s' % (
                         str(block_dict['name']),
                         str(block_dict['old_X']),
                         str(block_dict['old_Y']),
                         str(block_dict['new_X']),
                         str(block_dict['new_Y']),
                         str(block_dict['width']),
                         str(block_dict['height'])
                         )
        block_object_list.append(block_sub_string)
      block_string = '*'.join(block_object_list)
      return block_string
    else:
      return block_string


  def getBlockObject(self, block_name, content_list):
    """
    recover the block related to the block_name inside the content_list
    """
    for block in content_list:
      if block.name == block_name:
        return block


  def getDestinationGroup(self, structure, block_moved, axis_groups,
                                group_position, group_length):
    """
    recover destination group from block coordinates and main axis coordinates
    block_moved is a dict of properties.
    returns the group object itself, none if the block has no good coordinates
    """
    good_group_name = ''
    # recovering group name
    for axis_name in axis_groups.keys():
      if  axis_groups[axis_name][group_position] < block_moved['center'] and \
          axis_groups[axis_name][group_position] + \
          axis_groups[axis_name][group_length] > block_moved['center']:
        # the center of the block is between group min and max bounds
        # the group we are searching for is known
        good_group_name = axis_name
        break
    # if no group is found, this means the block is outside the bounds
    if good_group_name == '':
      return None
    # group name is known, searching corresponding group object
    for group in structure.planning.main_axis.axis_group:
      if group.name == good_group_name:
        return group
    return None



  def getDestinationBounds(self, structure, block_moved, block_object,
                                 planning_coordinates, axis_length,
                                 destination_group=None):
    """
    check the new bounds of the block over the secondary axis according to its
    new position
    """
    error = 0
    # XXX CALENDAR
    # has to be improved : for now the axis bounds are recovered globally, it
    # implies that all groups have the same bounds, which is not the case in
    # calendar mode. for that will need to add special informations about the
    # group itself to know its own bounds.
    # => In case of calendar mode, axis_bounds are recovered from the
    #    destination group instead of the planning itself

    delta_start = block_moved['secondary_axis_position'] / \
                  planning_coordinates['frame']['planning_content'][axis_length]
    delta_stop  = (block_moved['secondary_axis_position'] + \
                  block_moved['secondary_axis_length']) / \
                  planning_coordinates['frame']['planning_content'][axis_length]

    # testing different cases of invalidation
    if delta_stop < 0 or delta_start > 1 :
      # block if fully out of the bounds
      # can not validate it : returning None
      error = 1
    else:
      if delta_start < 0 or delta_stop > 1:
        # part of the block is inside
        # should handle support for correcting bounds : user should not be able
        # to define any data out of its group bounds.
        pass

    if structure.basic.calendar_mode:
      axis_range = destination_group.secondary_axis_range
      new_start = destination_group.secondary_axis_start + \
                  delta_start * axis_range
      new_stop = destination_group.secondary_axis_start + \
                  delta_stop * axis_range
    else:
      axis_range = structure.basic.secondary_axis_info['bound_stop'] - \
                   structure.basic.secondary_axis_info['bound_start']

      # defining new final block bounds
      new_start = structure.basic.secondary_axis_info['bound_start'] + \
                  delta_start * axis_range
      new_stop  = structure.basic.secondary_axis_info['bound_start'] + \
                  delta_stop * axis_range

    return [new_start,new_stop, error]



  def getActivityBounds(self, activity, activity_block_moved_list,
                              activity_block_list):
    """
    Recompose Activity from moved blocks.
    Warning : in case of calendar view, object bounds are not recomposed : only
              bounds of each activity are calculated, not object bounds !

    takes a list with modified blocks and another one with original blocks,
    returning new startactivity_block_moved_list & stop for the activity
    BEWARE : in case an activity bound was cut off to fit planning size, the
    value will not be updated (as the block was not on the real activity bound)
    """
    # getting list moved block names
    block_moved_name_list = map(lambda x: x['block_moved']['name'],
                                activity_block_moved_list)


    for activity_block in activity_block_list:
      if activity_block.name in block_moved_name_list:
        # the block composing the activity has been moved, not taking care of
        # the original one, but only the final position (block_moved)
        for temp_block_moved in activity_block_moved_list:
          # recovering corresponding moved block
          if temp_block_moved['block_moved']['name'] == activity_block.name:
            # moved block has been found
            temp_start = temp_block_moved['block_moved']['secondary_axis_start']
            temp_stop  = temp_block_moved['block_moved']['secondary_axis_stop']
            break
      else:
        # the block has not been moved
        temp_start = activity_block.position_secondary.absolute_begin
        temp_stop  = activity_block.position_secondary.absolute_end
      # once the start & stop values are recovered, need to test them to check
      # if it is needed to update
      try:
        if temp_start < new_start:
          new_start = temp_start
        if temp_stop > new_stop:
          new_stop = temp_stop
      except NameError:
        # new_start is not defined because it is the first block found
        new_start = temp_start
        new_stop = temp_stop

    # new start & stop values are known
    # checking weither activity has been cut-off to fit the planning bounds 
    #if activity.secondary_axis_begin != activity.secondary_axis_start:
    #  new_start = activity.secondary_axis_begin
    #if activity.secondary_axis_end != activity.secondary_axis_stop:
    #  new_stop  = activity.secondary_axis_end

    return [new_start,new_stop]


  def getObjectDict(self, structure):
    """
    Takes all activities related to a specified object and return
    """
    # init dict
    object_dict = {}
    # get property_names
    start_property = structure.basic.field.get_value('x_start_bloc')
    stop_property = structure.basic.field.get_value('x_stop_bloc')
    # get full axis length
    axis_start = structure.basic.secondary_axis_info['bound_start']
    axis_stop  = structure.basic.secondary_axis_info['bound_stop']
    for axis_group in structure.planning.main_axis.axis_group:
      for axis_element in axis_group.axis_element_list:
        for activity in axis_element.activity_list:
          # for each activity, saving its properties into a dict
          if activity.link in object_dict.keys():
            object_dict[activity.link].append(
                       { 'activity_name' : activity.name,
                         'axis_start': activity.secondary_axis_start,
                         'axis_stop' : activity.secondary_axis_stop
                       })
          else:
            # need to add object start & stop properties
            object_start = activity.object.getProperty(start_property)
            object_stop = activity.object.getProperty(stop_property)
            # check if need to update start and stop.
            # according to general specifications, this can be done only if the
            # original object is not cut to fit view bounds :min and max bounds
            if object_start < axis_start:
              bound_start = 'no'
            else:
              bound_start = 'yes'
            if object_stop > axis_stop:
              bound_stop = 'no'
            else:
              bound_stop = 'yes'
            object_dict[activity.link] = \
                       [{ 'activity_name' : 'update',
                          'axis_start' : bound_start,
                          'axis_stop'  : bound_stop
                         }]
            # adding activity properties
            object_dict[activity.link].append(
                       { 'activity_name' : activity.name,
                         'axis_start': activity.secondary_axis_start,
                         'axis_stop' : activity.secondary_axis_stop
                       })
    return object_dict


class PlanningBoxWidget(Widget.Widget):
  """
  PlanningBox main class used to run all the process in order to generate
  the structure of the Planning including all internal properties.
  Contains BasicStructure and PlanningStructure instances
  """



  property_names = Widget.Widget.property_names +\
  ['js_enabled',
   # kind of display : horizontal or vertical
   'calendar_view',
   # number of groups over the main axis
   'main_axis_groups',
   # width properties
   'size_border_width_left','size_planning_width','size_y_axis_space',
   'size_y_axis_width',
   # height properties
   'size_header_height','size_planning_height','size_x_axis_space',
   'size_x_axis_height',
   # axis position
   'y_axis_position', 'x_axis_position',
   'report_root_list','selection_name',
   'portal_types','sort',
   'list_method',
   # method used to get title of each line
   'title_line',
   # specific block properties
   'x_start_bloc','x_stop_bloc', 'y_size_block',
   # name of scripts 
   'stat_method','split_method','color_script',
   'round_script','sec_axis_script',
   # number of delimitations over the secondary axis
   'delimiter',
   # specific methods for inserting info block
   'info_center','info_topleft','info_topright',
   'info_backleft','info_backright'
   ]

  # Planning properties (accessed through Zope Management Interface)

  # kind of representation to render :
  # Planning or Calendar
  js_enabled = fields.CheckBoxField('js_enabled',
      title='enable on the fly edition (based on java script)',
      description='define if javascript is enabled or not on the current Planning',
      default=1,
      required=1)

  # kind of representation to render :
  # Planning or Calendar
  calendar_view = fields.CheckBoxField('calendar_view',
      title='calendar view (vertical view)',
      description='define if need to changes axis order. By default Y axis is'
                  'main axis, but to displa calendar main axis must be X one.',
      default=0,
      required=1)

  # added especially for new Planning Structure generation
  # is used to split result in pages in a ListBox like rendering
  # (delimitation over the main axis)
  main_axis_groups = fields.IntegerField('main_axis_groups',
      title='groups per page on main axis',
      description=('number of groups displayed per page on main axis'),
      default=10,
      required=1)

  # setting header height
  size_header_height = fields.IntegerField('size_header_height',
      title='header height',
      desciption=(
      'height of the planning header'),
      default=100,
      required=1)

  # setting left border size
  size_border_width_left = fields.IntegerField('size_border_width_left',
      title='Size border width left',
      desciption=(
      'setting left border size'),
      default=10,
      required=1)

  # setting the width of the Planning (excl. Y axis : only the block area)
  size_planning_width = fields.IntegerField('size_planning_width',
      title='Planning width',
      desciption=(
      'size of the planning area, excluding axis size'),
      default=1000,
      required=1)

  # setting the with of the Y axis
  size_y_axis_width = fields.IntegerField('size_y_axis_width',
      title='Y axis width',
      description=(
      'width of the Y axis'),
      default=200,
      required=1)

  # setting the with of the space (between Planning and Y axis)
  size_y_axis_space = fields.IntegerField('size_y_axis_space',
      title='Y axis space',
      description=(
      'space between Y axis and PLanning content'),
      default=10,
      required=1)

  # setting the height of the Planning (excl. X axis)
  size_planning_height = fields.IntegerField('size_planning_height',
      title='Planning height',
      description=(
      'size of the planning area, excluding axis_size'),
      default=800,
      required=1)

  # setting the height of the X axis
  size_x_axis_height = fields.IntegerField('size_x_axis_height',
      title='X axis height',
      description=(
      'height of the X axis'),
      default=200,
      required=1)

  # setting the height of the space (between Planning and X axis)
  size_x_axis_space = fields.IntegerField('size_x_axis_space',
      title='X axis space',
      description=(
      'space between X axis and Planning content '),
      default=10,
      required=1)


  y_axis_position = fields.CheckBoxField('y_axis_position',
      title='Force Y axis to the right intead of left',
      description=('position of Y axis over the planning content.'
                   'If checked, the Y axis will match the right border'
                   'of the planning, otherwise default is applied : left'),
      default = 0,
      required = 1)

  x_axis_position = fields.CheckBoxField('x_axis_position',
      title='Force X axis to the bottom instead of top',
      description=('position of X axis over the planning content.'
                   'default is top, if checked then right apply'),
      default = 0,
      required = 1)


  default = fields.TextAreaField('default',
      title='Default',
      description=(
      "Default value of the text in the widget."),
      default="",
      width=20, height=3,
      required=0)


  delimiter = fields.IntegerField('delimiter',
      title='min number of delimiters over the secondary axis',
      description=("min number of delimitations over the sec axis, required"),
      default = 5,
      required=1)


  report_root_list = fields.ListTextAreaField('report_root_list',
      title="Report Root",
      description=("A list of domains which define the possible root."),
      default=[],
      required=0)


  selection_name = fields.StringField('selection_name',
      title='Selection Name',
      description=("The name of the selection to store selections params"),
      default='planning_0',
      required=1)


  portal_types = fields.ListTextAreaField('portal_types',
      title="Portal Types",
      description=("Portal Types of objects to list. Required."),
      default=[],
      required=0)


  sort = fields.ListTextAreaField('sort',
      title='Default Sort',
      description=("The default sort keys and order"),
      default=[],
      required=0)


  list_method = fields.MethodField('list_method',
      title='List Method',
      description=("Method to use to list objects"),
      default='searchFolder',
      required=0)


  title_line = fields.StringField('title_line',
      title="specific method which fetches the title of each line",
      description=("specific method for inserting title in line"),
      default='',
      required=0)




  x_start_bloc = fields.StringField('x_start_bloc',
      title='specific property to get start of blocks (ex. start_date)',
      description=('Property for building X-Axis such as start_date\
      objects'),
      default='start_date',
      required=0)

  x_stop_bloc = fields.StringField('x_stop_bloc',
      title='specific property to get stop of blocks (ex. stop_date)',
      description=('Property for building X-Axis such as stop_date\
      objects'),
      default='stop_date',
      required=0)

  y_size_block = fields.StringField('y_size_block',
      title='specific property to get height of blocks (ex.quantity)',
      description=('Method for building height of blocks objects'),
      default='quantity',
      required=0)


  constraint_method = fields.StringField('constraint_method',
      title='name of constraint method between blocks',
      description=('Constraint method between blocks objects'),
      default='SET_DHTML',
      required=1)

  stat_method = fields.StringField('stat_method',
      title="name of script generating statistics",
      description=("script for statistics"),
      default='',
      required=0)

  split_method = fields.StringField('split_method',
      title='name of script splitting activities into blocks',
      description=("script for splitting activities into multiple blocks"),
      default='',
      required=0)

  color_script = fields.StringField('color_script',
      title='name of script colorizing blocks',
      description=('script for block colors object'),
      default='',
      required=0)

  round_script = fields.StringField('round_script',
      title='name of script rounding blocks during validation (ex.\
            Planning_roundBoundToDay)',
      description=('script for block bounds rounding when validating'),
      default='',
      required=0)


  sec_axis_script = fields.StringField('sec_axis_script',
      title='name of script building secondary axis (ex.\
            Planning_generateAxis)',
      description=('script for building secondary axis'),
      default='Planning_generateAxis',
      required=1)


  info_center = fields.StringField('info_center',
      title='specific method of data called for inserting info in\
      block center',
      description=('Method for displaying info in the center of a\
      block object'),
      default='',
      required=0)

  info_topright = fields.StringField('info_topright',
      title='specific method of data called for inserting info in\
      block topright',
      description=('Method for displaying info in the topright of a block\
      object'),
      default='',
      required=0)

  info_topleft = fields.StringField('info_topleft',
      title='specific method of data called for inserting info in\
      block topleft',
      description=('Method for displaying info in the topleft corner\
      of a block object'),
      default='',
      required=0)

  info_backleft = fields.StringField('info_backleft',
      title='specific method of data called for inserting info in\
      block backleft',
      description=('Method for displaying info in the backleft of a\
      block object'),
      default='',
      required=0)

  info_backright = fields.StringField('info_backright',
      title='specific method of data called for inserting info in\
      block backright',
      description=('Method for displaying info in the backright of a\
      block object'),
      default='',
      required=0)

  security_index = fields.IntegerField('security_index',
      title='variable depending on the type of web browser :',
      description=("This variable is used because the rounds of each\
      web browser seem to work differently"),
      default=2,
      required=0)



  def render_css(self,field, key, value, REQUEST):
    """
    first method called for rendering by PageTemplate form_view
    create the whole object based structure, and then call a special
    external PageTemplate (or DTML depending) to render the CSS code
    relative to the structure that need to be rendered
    """

    here = REQUEST['here']

    #import pdb
    #pdb.set_trace()
    # build structure
    # render_structure will call all method necessary to build the entire
    # structure relative to the planning
    # creates and fill up self.basic, self.planning and self.build_error_list
    self.render_structure(field=field, key=key, value=value,
                                    REQUEST=REQUEST, here=here)



    # getting CSS script generator
    planning_css_method = getattr(REQUEST['here'],'planning_css')
    # recover CSS data buy calling DTML document
    CSS_data = planning_css_method(structure=self)
    # saving structure inside the request for HTML render
    REQUEST.set('structure',self)

    return CSS_data



  def render(self,field,key,value,REQUEST):
    """
    method called to render the HTML code relative to the planning.
    for that recover the structure previouly saved in the REQUEST, and then
    call a special Page Template aimed to render
    """
    # need to test if render is HTML (to be implemented in a page template)
    # or list (to generated a PDF output or anything else).

    # recover structure
    structure = REQUEST.get('structure')


    #pdb.set_trace()

    # getting HTML rendering Page Template
    planning_html_method = getattr(REQUEST['here'],'planning_content')
    # recovering HTML data by calling Page Template document
    HTML_data = planning_html_method(struct=structure)
    # return HTML data
    return HTML_data


  def render_structure(self, field, key, value, REQUEST, here):
    """ this method is the begining of the rendering procedure. it calls all
        methods needed to generate BasicStructure with ERP5 objects, and then
        creates the PlanningStructure before applying zoom.
        No code is generated (for example HTML code) contrary to the previous
        implementation of PlanningBox. The final rendering must be done through
        a PageTemplate parsing the PlanningStructure object.
        """
    # XXX testing : uncoment to put selection to null => used for debugging
    #here.portal_selections.setSelectionFor(selection_name, None)



    ####### DATA DEFINITION #######
    self.build_error_list = None
    # recovering usefull planning properties
    form = field.aq_parent # getting form
    list_method = field.get_value('list_method') # method used to list objects
    report_root_list = field.get_value('report_root_list') # list of domains
    portal_types = field.get_value('portal_types') # Portal Types of objects
    # selection name used to store selection params
    selection_name = field.get_value('selection_name')
    # getting sorting keys and order (list)
    sort = field.get_value('sort')
    # contains the list of blocks that are not validated
    # for them a special rendering is done (special colors for example)
    list_error=REQUEST.get('list_block_error')
    if list_error==None : list_error = []
    selection = here.portal_selections.getSelectionFor(
                      selection_name, REQUEST)
    # params contained in the selection object is a dictionnary.
    # must exist as an empty dictionnary if selection is empty.
    try:
      params = selection.getParams()
    except (AttributeError,KeyError):
      params = {}

    #pdb.set_trace()
    ###### CALL CLASS METHODS TO BUILD BASIC STRUCTURE ######
    # creating BasicStructure instance (and initializing its internal values)
    self.basic = BasicStructure(here=here,form=form, field=field,
                                REQUEST=REQUEST, list_method=list_method,
                                selection=selection, params = params,
                                selection_name=selection_name,
                                report_root_list=report_root_list,
                                portal_types=portal_types, sort=sort,
                                list_error=list_error)
    # call build method to generate BasicStructure
    status = self.basic.build()
    if status != 1:
      self.build_error_list = status
      return self

    ###### CALL CLASS METHODS TO BUILD PLANNING STRUCTURE ######
    # creating PlanningStructure instance and initializing its internal values
    self.planning = PlanningStructure()
    # call build method to generate final Planning Structure
    status = self.planning.build(basic_structure = self.basic,field=field,
                                 REQUEST=REQUEST)
    if status != 1:
      # in case error during planning structure generation
      self.build_error_list = status
      return self

    return self

# instanciating class
PlanningBoxWidgetInstance = PlanningBoxWidget()

class BasicStructure:
  """
  First Structure recovered from ERP5 objects. Does not represent in any
  way the final structure used for rendering the Planning (for that see
  PlanningStructure class). for each returned object from ERP5's request,
  create a BasicGroup and stores all object properties.
  No zoom is applied on this structure
  """

  def __init__ (self, here='', form='', field='', REQUEST='', list_method='',
    selection=None, params = '', selection_name='', report_root_list='',
    portal_types='', sort=None, list_error=None):
    """ init main internal parameters """
    self.here = here
    self.form = form
    self.field = field
    self.REQUEST = REQUEST
    self.sort = sort
    self.selection = selection
    self.params = params
    self.list_method = list_method
    self.selection_name = selection_name
    self.report_root_list = report_root_list
    self.portal_types = portal_types
    self.basic_group_list = None
    self.report_groups= '' # needed to generate groups
    self.list_error = list_error

    self.secondary_axis_occurence = []
    self.render_format = '' # 'list' in case output is a list containing the
                            # full planning structure without any selection
    self.main_axis_info = {}
    self.secondary_axis_info = {}


  def build(self):
    """
    build BasicStructure from given parameters, and for that do the
    specified processes :
    1 - define variables
    2 - building query
    3 - generate report_tree, a special structure containing all the
        objects with their values
    4 - create report_sections
    """

    default_params ={}
    current_section = None
    #params = self.selection.getParams()


    #recovering selection if necessary
    if self.selection is None:
      self.selection = Selection(params=default_params,
                                 default_sort_on=self.sort)
    else:
      # immediately updating the default sort value
      self.selection.edit(default_sort_on=self.sort)
      self.selection.edit(sort_on=self.sort)

    self.here.portal_selections.setSelectionFor(self.selection_name,
                                        self.selection,REQUEST=self.REQUEST)

    # building list of portal_types
    self.filtered_portal_types = map(lambda x: x[0], self.portal_types)
    if len(self.filtered_portal_types) == 0:
      self.filtered_portal_types = None

    report_depth = self.REQUEST.get('report_depth',None)
    # In report tree mode, need to remember if the items have to be displayed
    is_report_opened = self.REQUEST.get('is_report_opened',\
                                    self.selection.isReportOpened())
    self.selection.edit(report_opened=is_report_opened)
    portal_categories = getattr(self.form,'portal_categories',None)
    portal_domains = getattr(self.form,'portal_domains',None)



    ##################################################
    ############### BUILDING QUERY ###################
    ##################################################
    kw = self.params
    # remove selection_expression if present
    # This is necessary for now, because the actual selection expression in
    # search catalog does not take the requested columns into account. If
    # select_expression is passed, this can raise an exception, because stat
    # method sets select_expression, and this might cause duplicated column
    # names.
    if 'select_expression' in kw:
      del kw['select_expression']
    if hasattr(self.list_method, 'method_name'):
      if self.list_method.method_name == 'ObjectValues':
        # list_method is available
        self.list_method = self.here.objectValues
        kw = copy(self.params)
      else:
        # building a complex query so we should not pass too many variables
        kw={}
        if self.REQUEST.form.has_key('portal_type'):
          kw['portal_type'] = self.REQUEST.form['portal_type']
        elif self.REQUEST.has_key('portal_type'):
          kw['portal_type'] = self.REQUEST['portal_type']
        elif self.filtered_portal_types is not None:
          kw['portal_type'] = self.filtered_portal_types
        elif kw.has_key('portal_type'):
          if kw['portal_type'] == '':
            del kw['portal_type']
        # remove useless matter
        for cname in self.params.keys():
          if self.params[cname] != '' and self.params[cname] != None:
            kw[cname] = self.params[cname]
        # try to get the method through acquisition
        try:
          self.list_method = getattr(self.here, self.list_method.method_name)
        except (AttributeError, KeyError):
          pass
    elif self.list_method in (None,''):
      # use current selection
      self.list_method = None

    ##################################################
    ############## DEFINING STAT METHOD ##############
    ##################################################
    stat_method = self.field.get_value('stat_method')
    stat_method = getattr(self.here,stat_method, None)
    if stat_method == None:
      show_stat = 0
    else:
      show_stat = 1


    ##################################################
    ############ BUILDING REPORT_TREE ################
    ##################################################
    # assuming result is report tree, building it
    # When building the body, need to go through all report lines
    # each report line is a tuple of the form :
    #(selection_id, is_summary, depth, object_list, object_list_size, is_open)

    try:
      default_selection_report_path = self.report_root_list[0][0].split('/')[0]
    except (IndexError):
      message = 'report path is empty or not valid, please check selection\
                 report path in Planning properties'
      return [(Message(domain=None, message=message,mapping=None))]
    if (default_selection_report_path in portal_categories.objectIds()) or \
      (portal_domains is not None and default_selection_report_path in \
       portal_domaind.objectIds()):
      pass
    else:
      default_selection_root_path = self.report_root_list[0][0]
    self.selection_report_path = self.selection.getReportPath(default = \
     (default_selection_report_path,))

    if self.selection_report_path in (None,()):
      message = 'report path is empty or not valid'
      return [(Message(domain=None, message=message,mapping=None))]

    # testing report_depth value
    if report_depth is not None:
      selection_report_current = ()
    else:
      selection_report_current = self.selection.getReportList()

    # building report_tree_list
    report_tree_list = makeTreeList(here=self.here, form=self.form,
                                    root_dict=None,
                                    report_path=self.selection_report_path,
                                    base_category=None, depth=0,
                                    unfolded_list=selection_report_current,
                                    selection_name=self.selection_name,
     report_depth=report_depth,is_report_opened=is_report_opened,
     sort_on=self.selection.sort_on,form_id=self.form.id)

    ##################################################
    ########### BUILDING REPORT_GROUPS ###############
    ##################################################
    # report_groups is another structure based on report_tree but
    # taking care of the object activities.
    # build two structures :
    # - report_groups : list of object_tree_lines composing the planning,
    #   whatever the current group depth, just listing all of them
    # - blocks_object : dict (object_tree_line.getObject()) of objects
    # (assuming objects is a list of activities).

    # first init parameters
    self.report_groups = []
    list_object = []
    self.nbr_groups=0
    object_list=[]
    self.report_activity_dict = {}
    indic_line=0
    index_line=0
    blocks_object={} 
    select_expression = ''

    # now iterating through report_tree_list
    for object_tree_line in report_tree_list:
      # prepare query by defining selection report object
      self.selection.edit(report = object_tree_line.getSelectDomainDict())

      # defining info_dict, holding all information about the current object.
      info_dict = None
      info_dict = {}

      if object_tree_line.getIsPureSummary() and show_stat:

        info_dict['stat'] = 1

        # push new select_expression
        original_select_expression = kw.get('select_expression')
        kw['select_expression'] = select_expression
        self.selection.edit(params = kw)
        # recovering statistics if needed
        # getting list of statistic blocks
        stat_list = stat_method(selection=self.selection,
                                list_method=self.list_method,
                                selection_context=self.here,
                                report_tree_list=report_tree_list,
                                object_tree_line=object_tree_line,
                                REQUEST=self.REQUEST, field=self.field)

        if original_select_expression is None:
          del kw['select_expression']
        else:
          kw['select_expression'] = original_select_expression

        # adding current line to report_section where
        # line is pure Summary
        self.report_groups += [(object_tree_line,stat_list,info_dict)]
        self.nbr_groups += 1

      else:
        info_dict['stat'] = 0

        # processing all cases
        self.selection.edit(params = kw)

        # recovering object list
        if self.list_method not in (None,''):
          # valid list_method has been found
          self.selection.edit(exception_uid_list= \
             object_tree_line.getExceptionUidList())
          object_list = self.selection(method = self.list_method,
             context=self.here, REQUEST=self.REQUEST)
        else:
          # no list_method found
          # XXX seems to be buggy :
          #object_list = self.here.portal_selections.getSelectionValueList(
          #  self.selection_name, context=self.here, REQUEST=self.REQUEST)
          message = 'No list method found, please check planningBox properties'
          return [(Message(domain=None, message=message,mapping=None))]

        # recovering exeption_uid_list
        exception_uid_list = object_tree_line.getExceptionUidList()
        if exception_uid_list is not None:
          # Filter folders if parent tree :
          # build new object_list for current line
          # (list of relative elements)
          new_object_list = []
          for selected_object in object_list:
            if selected_object.getUid() not in exception_uid_list:
              new_object_list.append(selected_object)
          object_list = new_object_list

        if not object_tree_line.getIsPureSummary():
          # Object is not pure summary
          if show_stat:
            # this represents the second duplicated object
            # display object content in report tree with stat
            # stats are displayed in the first object present
            #
            self.report_groups += [(object_tree_line,object_list, info_dict)]
            self.nbr_groups += 1
          else:
            # do nothing
            # case of parent tree unfolded (second object and no stats)
            pass
        else:
          # object is pure summary !
          if len(object_list) and object_tree_line.is_open:
            # pure summary, open, and has object_list
            # case = ?!?
            self.report_groups += [(object_tree_line, object_list, info_dict)]
            self.nbr_groups += 1
          else:
            if exception_uid_list is not None:
              # case of parent tree mode (first/unique object).
              # beware object_list is not null in case folded sons exists so
              # do not export voluntary object_list to prevent bad
              # interpretation
              self.report_groups += [(object_tree_line, [], info_dict)]
              self.nbr_groups += 1
            else:
              # case of report_tree mode
              # saving information in report_groups
              self.report_groups += [(object_tree_line,object_list,info_dict)]
              self.nbr_groups += 1



    # reset to original value
    self.selection.edit(report = None)
    #self.selection.edit(report_list=None) # comment to save report_list status

    # update report list if report_depth was specified
    if report_depth is not None:
      unfolded_list = []
      for (report_line, object_list, info_dict) in self.report_groups:
        if report_line.depth < report_depth and not info_dict['stat'] :
          # depth of current report_line is inferior to the current
          # report_depth and current report_line is not stat line.
          # saving information
          unfolded_list.append(report_line.getObject().getRelativeUrl())
      self.selection.edit(report_list=unfolded_list)


    ##################################################
    ############## CHECKING CONSTRAINTS ##############
    ##################################################
    # XXX Constraints checking chould be called here
    # and results saved in a list (list of url corresponding to objects not
    # validated)

    ##################################################
    ########### GETTING MAIN AXIS BOUNDS #############
    ##################################################
    # before building group_object structure, need to recover axis begin & end
    # for main to be able to generate a 'smart' structure taking into account
    # only the area that need to be rendered. This prevents from useless
    # processing
    # calculating main axis bounds
    self.getMainAxisInfo(self.main_axis_info)
    # applying main axis selection
    if self.report_groups != []:
      self.report_groups=self.report_groups[self.main_axis_info['bound_start']:
                                            self.main_axis_info['bound_stop']]
    else:
      # ERROR : self.report_groups = []
      # no group is available so the Y and X axis will be empty...
      message= 'selection method returned empty list of objects : please check\
                your list_method and report_root'
      return [(Message(domain=None, message=message,mapping=None))]


    #pdb.set_trace()

    ##################################################
    ############ GETTING SEC AXIS BOUNDS #############
    ##################################################
    # now that our report_group structure has been cut need to get secondary
    # axis bounds to add only the blocs needed afterwards
    # getting secondary_axis_occurence to define begin and end secondary_axis
    # bounds (getting absolute size)
    self.getSecondaryAxisOccurence()
    # XXX changing point of view to handle axis occurences : their are now
    # handled by group, so that it is easy to recover group bounds in case the
    # current rendering is calendar mode.

    # now getting start & stop bounds (getting relative size to the current
    # rendering)
    status = self.getSecondaryAxisInfo(self.secondary_axis_info)
    if status != 1:
      # ERROR
      # Found error while setting secondary axis bounds
      return status


    ##################################################
    ####### SAVING NEW PROPERTIES INTO REQUEST #######
    ##################################################
    if self.list_method is not None and self.render_format != 'list':
     self.selection.edit(params = self.params)
     self.here.portal_selections.setSelectionFor(self.selection_name,
                                                 self.selection,
                                                 REQUEST = self.REQUEST)


    ##################################################
    ######### BUILDING GROUP_OBJECT STRUCTURE ########
    ##################################################
    # building group_object structure using sub lines depth (in case of a
    # report tree) by doing this.
    # taking into account page bounds to generate only the structure needed
    # instanciate BasicGroup class in BasicStructure so that the structure can
    # be built
    status = self.buildGroupStructure()
    if status != 1:
      # ERROR
      # Found errors while setting group structure
      return status
    # everything is fine
    return 1



  def getSecondaryAxisOccurence(self):
    """
    get secondary_axis occurences in order to define begin and end bounds.
    Just make a listing of all the start and stop values for all the
    report_group objects
    """
    secondary_axis_occurence = []
    #pdb.set_trace()

    # defining the objects requested for calendar mode testing
    if self.selection_report_path == 'parent':
      calendar_mode = 0
    else:
      calendar_mode = 1 # assuming calendar_mode = 1 by default.
    calendar_range = 0  # range max on the current calendar mode. used for
                        # example while dealing with months : 31 is saved as
                        # the largest range, even if some month have only 28
                        # to 30 days

    # specific start & stop methods name for secondary axis
    start_property_id = self.field.get_value('x_start_bloc')
    stop_property_id= self.field.get_value('x_stop_bloc')
    for (object_tree_group, object_list, info_dict) in self.report_groups:

      # defining empty list for each kind of occurence.
      group_list = None
      group_list = []
      item_list = None
      item_list = []

      # recovering group_properties
      if start_property_id != None:
        group_start = \
        object_tree_group.object.getObject().getProperty(start_property_id,
                                                         None)
        if object_tree_group.object.getObject().hasProperty('start_date'):
          group_start = \
          object_tree_group.object.getObject().start_date
      else:
        group_start= None
      if stop_property_id != None:
        group_stop = \
        object_tree_group.object.getObject().getProperty(stop_property_id,None)
        if object_tree_group.object.getObject().hasProperty('stop_date'):
          group_stop = \
          object_tree_group.object.getObject().stop_date
      else:
        group_stop = None

      group_list = [[group_start, group_stop]]

      # no calendar mode available if group has no valid bounds.
      if None in [group_start,group_stop]:
        calendar_mode = 0
      else:
        # seems to be a valid calendar mode, checking if need to update
        # calendar_range
        if calendar_range < (group_stop - group_start):
          calendar_range = (group_stop - group_start)


      # recovering item properties
      if object_list not in (None, [], {}) :
        for object_request in object_list:
          if start_property_id != None:
            block_begin = \
            object_request.getObject().getProperty(start_property_id,None)
          else:
            block_begin = None
          if stop_property_id != None:
            block_stop = \
            object_request.getObject().getProperty(stop_property_id,None)
          else:
            block_stop = None
          item_list.append([block_begin,block_stop])

          # testing if current item is compliant with calendar mode
          # i.e item car be represented within the current group
          if calendar_mode and (block_stop <= group_start) and \
                               (block_begin >= group_stop):
            # invalid conditions : item outside group, so no calendar mode
            calendar_mode = 0

        # adding list of items to group_list
        group_list.extend(item_list)

      # adding current group list to list of occurences
      secondary_axis_occurence.extend(group_list)

    # saving resulting values.
    self.calendar_mode  = calendar_mode
    self.calendar_range = calendar_range
    self.secondary_axis_occurence =  secondary_axis_occurence



  def getSecondaryAxisInfo(self, axis_dict):
    """
    secondary_axis_ocurence holds couples of data (begin,end) related to
    basicActivity blocks, and axis if the instance representing the sec axis.
    it is now possible to recover begin and end value of the planning and then
    apply selection informations to get start and stop.
    """

    # recovering zoom properties
    axis_dict['zoom_start'] = int(self.params.get('zoom_start',0))
    axis_dict['zoom_level'] = float(self.params.get('zoom_level',1))

    # recovering min and max bounds to get absolute bounds
    axis_dict['bound_begin'] = self.secondary_axis_occurence[0][0]
    axis_dict['bound_end'] = axis_dict['bound_begin']
    for occurence in self.secondary_axis_occurence:
      if (occurence[0] < axis_dict['bound_begin'] or \
          axis_dict['bound_begin'] == None) and occurence[0] != None:
        axis_dict['bound_begin'] = occurence[0]
      if (occurence[1] > axis_dict['bound_end'] or  \
          axis_dict['bound_end'] == None) and occurence[1] != None:
        axis_dict['bound_end'] = occurence[1]

    if axis_dict['bound_end']==None or axis_dict['bound_begin']==None:
      # ERROR
      # no bounds over the secondary axis have been defined
      # can append if bad property has been selected
      message = 'can not find secondary axis bounds for planning view :\
      No object has good start & stop properties, please check your objects \
      and their corresponding properties'
      return [(Message(domain=None, message=message,mapping=None))]


    axis_dict['bound_range'] = axis_dict['bound_end']-axis_dict['bound_begin']
    # now start and stop have the extreme values of the second axis bound.
    # this represents in fact the size of the Planning's secondary axis

    # can now get selection informations ( float range 0..1)
    axis_dict['bound_start'] = 0
    axis_dict['bound_stop'] = 1
    if self.selection != None:
      # selection is not None, trying to recover previously saved values about
      # secondary axis (axis start and stop bounds)
      try:
        axis_dict['bound_start'] = self.selection.getSecondaryAxisStart()
        axis_dict['bound_stop'] = self.selection.getSecondaryAxisStop()
      except AttributeError:
        # bounds were not defined, escaping test
        pass

    # getting secondary axis page step
    axis_zoom_step = axis_dict['bound_range'] / axis_dict['zoom_level']

    # now setting bound_start
    axis_dict['bound_start'] = axis_dict['zoom_start'] * axis_zoom_step + \
                               axis_dict['bound_begin']
    # for bound_stop just add page step
    axis_dict['bound_stop'] = axis_dict['bound_start'] + axis_zoom_step

    # saving current zoom values
    self.params['zoom_level'] = axis_dict['zoom_level']
    self.params['zoom_start'] = axis_dict['zoom_start']

    # everything is OK, returning 'true' flag
    return 1


  def getMainAxisInfo(self, axis_dict):
    """
    getting main axis properties (total pages, current page, groups per page)
    and setting selection bounds (start & stop).
    beware this justs calculate the position of the first group present on the
    page (same for the last one), applying the selection is another thing in
    case of report tree (if the first element is a sub group of a report for
    example).
    """
    axis_dict['bound_axis_groups'] = self.field.get_value('main_axis_groups')
    if axis_dict['bound_axis_groups'] == None:
      #XXX raise exception : no group nb/page defined
      pass


    # setting begin & end bounds
    axis_dict['bound_begin'] = 0
    axis_dict['bound_end'] = len(self.report_groups)
    if self.render_format == 'list':
      axis_dict['bound_start'] = 0
      axis_dict['bound_stop'] = axis_dict['bound_end']
      axis_dict['bound_page_total'] = 1
      axis_dict['bound_page_current'] = 1
      axis_dict['bound_page_groups'] = 1
    else:
      # recovering first group displayed on actual page
      try:
        # trying to recover from REQUEST
        axis_dict['bound_start'] = self.REQUEST.get('list_start')
        axis_dict['bound_start'] = int(axis_dict['bound_start'])
      except (AttributeError, TypeError):
        # recovering from params is case failed with REQUEST
        axis_dict['bound_start'] = self.params.get('list_start',0)
        if type(axis_dict['bound_start']) is type([]):
          axis_dict['bound_start'] = axis_dict['bound_start'][0]
        axis_dict['bound_start'] = int(axis_dict['bound_start'])
      axis_dict['bound_start'] = max(axis_dict['bound_start'],0)

      if axis_dict['bound_start'] > axis_dict['bound_end']:
        # new report_group is so small that previous if after the last element
        axis_dict['bound_start'] = axis_dict['bound_end']

      # updating start position to fit page size.
      axis_dict['bound_start'] -= \
               (axis_dict['bound_start'] % axis_dict['bound_axis_groups'])

      # setting last group displayed on page
      axis_dict['bound_stop'] = min (axis_dict['bound_end'],
               axis_dict['bound_start'] + axis_dict['bound_axis_groups'])
      # calculating total number of pages
      axis_dict['bound_page_total'] = int(max(axis_dict['bound_end'] - 1,0) / \
               axis_dict['bound_axis_groups']) + 1
      # calculating current page number
      axis_dict['bound_page_current'] = int(axis_dict['bound_start'] / \
               axis_dict['bound_axis_groups']) + 1
      # adjusting first group displayed on current page
      axis_dict['bound_start'] = min(axis_dict['bound_start'], max(0,
           (axis_dict['bound_page_total']-1) * axis_dict['bound_axis_groups']))

      self.params['list_lines'] = axis_dict['bound_axis_groups']
      self.params['list_start'] = axis_dict['bound_start']


  def buildGroupStructure(self):
      """
      this procedure builds BasicGroup instances corresponding to the
      report_group_objects returned from the ERP5 request.
      """
      position = 0

      # iterating each element
      for (report_group_object, object_list, property_dict) in \
           self.report_groups:

        stat_result = {}
        stat_context = report_group_object.getObject().asContext(**stat_result)
        stat_context.domain_url = \
                     report_group_object.getObject().getRelativeUrl()
        stat_context.absolute_url = \
                     lambda x: report_group_object.getObject().absolute_url()
        url=getattr(stat_context,'domain_url','')
        # updating position_informations
        position +=1
        # recovering usefull informations, basic_structure
        title = report_group_object.getObject().getTitle()
        name = report_group_object.getObject().getTitle()
        depth = report_group_object.getDepth()
        is_open = report_group_object.getIsOpen()
        is_pure_summary = report_group_object.getIsPureSummary()

        # creating new group_object with all the informations collected
        group_start = group_stop = None
        if self.calendar_mode == 1:
          # recover start and stop of current object to generate good BasicGroup
          group_start = report_group_object.getObject().start_date
          group_stop  = report_group_object.getObject().stop_date -1
          # build dict to fix BasicActivity bounds
          secondary_axis_bounds = {}
          secondary_axis_bounds['bound_start'] = group_start
          secondary_axis_bounds['bound_stop']  = group_stop
        else:
          secondary_axis_bounds = self.secondary_axis_info
        child_group = BasicGroup(title=title, name=name, url=url,
                                 constraints=None, depth=depth,
                                 position=position, field =self.field,
                                 object=report_group_object, is_open=is_open,
                                 is_pure_summary=is_pure_summary,
                                 secondary_axis_start = group_start,
                                 secondary_axis_stop  = group_stop,
                                 property_dict = property_dict)


        if object_list != None:
          child_group.setBasicActivities(object_list,self.list_error,
                                         secondary_axis_bounds)

        try:
          self.basic_group_list.append(child_group)
        except (AttributeError):
          self.basic_group_list = []
          self.basic_group_list.append(child_group)

      return 1


class BasicGroup:
  """
  A BasicGroup holds informations about an ERP5Object and is stored
  exclusively in BasicStructure. for each activity that will need to be
  represented in the PlanningBox, a BasicActivity is created and added to
  the current structure (for example BasicGroup represents an employee,
  and each BasicActivity represents a task the employee has).
  *Only one BasicGroup present while in Calendar mode.
  *BasicGroup instance itself can hold other BasicGroups in case of
  ReportTree mode to handle child groups.
  """

  def __init__ (self, title='', name='',url='', constraints='', depth=0,
                position=0, field = None, object = None, is_open=0,
                is_pure_summary=1, secondary_axis_start=None,
                secondary_axis_stop=None, property_dict = {}):
    self.title = title
    self.name = name
    self.url = url
    self.basic_group_list = None # used with ReportTree
    self.basic_activity_list = None # bloc activities
    self.constraints = constraints# global contraints applying to all group
    self.depth = depth # depth of the actual group (report_tree mode)
    self.position = position # position of current group in the selection
    self.field = field # field object itself. used for several purposes
    self.object = object # ERP5 object returned & related to the group
    self.is_open = is_open
    self.is_pure_summary = is_pure_summary
    # specific start and stop bound values specifiec to the current group and
    # used in case of calendar mode
    self.secondary_axis_start = secondary_axis_start
    self.secondary_axis_stop = secondary_axis_stop
    # property_dict holds all information about the current axis_group
    # type of group, stat, etc.
    self.property_dict = property_dict


  def setBasicActivities(self,activity_list, list_error,secondary_axis_info):
    """
    link a list of activities to the current object.
    *Recover group properties. Used in case activity is built from Group
     itself
    *create a BasicActivity for each activity referenced in the list if
     necessary
    *add the activity to the current group.
    *update secondary_axis_occurence
    """
    info = {}
    # specific begin & stop property names for secondary axis
    object_property_begin = self.field.get_value('x_start_bloc')
    object_property_end = self.field.get_value('x_stop_bloc')
    # specific block text_information methods
    info_center = self.field.get_value('info_center')
    info_topleft = self.field.get_value('info_topleft')
    info_topright = self.field.get_value('info_topright')
    info_botleft = self.field.get_value('info_backleft')
    info_botright = self.field.get_value('info_backright')
    # getting info method from activity itself if exists
    info_center_method = getattr(self.object.getObject(),info_center,None)
    info_topright_method = getattr(self.object.getObject(),info_topright,None)
    info_topleft_method = getattr(self.object.getObject(),info_topleft,None)
    info_botleft_method = getattr(self.object.getObject(),info_botleft,None)
    info_botright_method = \
                  getattr(self.object.getObject(),info_botright,None)
    # if method recovered is not null, then updating
    if info_center_method!=None: 
      info['info_center'] = str(info_center_method())
    if info_topright_method!=None:
      info['info_topright'] = str(info_topright_method())
    if info_topleft_method!=None:
      info['info_topleft'] = str(info_topleft_method())
    if info_botleft_method!=None:
      info['info_botleft'] = str(info_botleft_method())
    if info_botright_method!=None:
      info['info_botright'] = str(info_botright_method())

    if activity_list not in ([],None):
      indic=0
      # iterating each activity linked to the current group
      for activity_content in activity_list:
        # interpreting results and getting begin and end values from 
        # previously recovered method
        block_begin = None
        block_end = None
        if object_property_begin !=None:
          block_begin = \
                 getattr(activity_content.getObject(),object_property_begin)
        else:
          block_begin = None

        if object_property_end != None:
          block_end = getattr(activity_content.getObject(),object_property_end)
        else:
          block_end = None

        # handling case where activity bound is not defined
        if block_begin == None:
          block_begin = secondary_axis_info['bound_start']
          current_color='#E4CCE1'
        if block_end == None:
          block_end = secondary_axis_info['bound_stop']
          current_color='#E4CCE1'
        # testing if activity is visible according to the current zoom
        # selection over the secondary_axis
        if  block_begin > secondary_axis_info['bound_stop'] or \
            block_end < secondary_axis_info['bound_start']:
          # activity will not be displayed, stopping process
          pass
        else:
          # activity is somehow displayed. checking if need to cut its bounds
          if block_begin < secondary_axis_info['bound_start']:
            # need to cut begin bound
            block_start = secondary_axis_info['bound_start']
          else: block_start = block_begin

          if block_end > secondary_axis_info['bound_stop']:
            block_stop = secondary_axis_info['bound_stop']
          else:
            block_stop = block_end

          # defining name
          name = "Activity_%s" % (str(indic))

          error = 'false'
          current_color=''

          if self.property_dict['stat'] == 1:
            info = None
            info = {}
            info['info_center'] = ''
            info['info_topright'] = ''
            info['info_topleft'] = ''
            info['info_botleft'] = ''
            info['info_botright'] = ''
            title = ''
            object = activity_content
            url=''
            object_property_height = self.field.get_value('y_size_block')
            height = \
                 getattr(activity_content.getObject(),object_property_height)
          else:
            info = None
            info = {}
            # getting info text from activity itself if exists
            info_center_method = getattr(activity_content,info_center,None)
            info_topright_method = getattr(activity_content,info_topright,None)
            info_topleft_method = getattr(activity_content,info_topleft,None)
            info_botleft_method = getattr(activity_content,info_botleft,None)
            info_botright_method = \
                 getattr(activity_content,info_botright,None)

            # if value recovered is not null, then updating 
            if info_center_method!=None:
               info['info_center']=str(info_center_method())
            if info_topright_method!=None:
               info['info_topright']=str(info_topright_method())
            if info_topleft_method!=None:
               info['info_topleft']=str(info_topleft_method())
            if info_botleft_method!=None:
               info['info_botleft'] =str(info_botleft_method())
            if info_botright_method!=None:
               info['info_botright']=str(info_botright_method())

            title = info['info_center']

            color_script = getattr(activity_content.getObject(),
                                   self.field.get_value('color_script'),None)
            # calling color script if exists to set up activity_color
            if color_script !=None:
              current_color = color_script(activity_content.getObject())

            # testing if some activities have errors
            if list_error not in (None, []):
              for activity_error in list_error:
                if activity_error[0][0] == name:
                  error = 'true'
                  break

            stat_result = {}
            stat_context = \
                         activity_content.getObject().asContext(**stat_result)
            stat_context.domain_url = \
                         activity_content.getObject().getRelativeUrl()
            stat_context.absolute_url = \
                         lambda x: activity_content.getObject().absolute_url()
            object = stat_context.getObject()
            url = stat_context.getUrl()

            # XXX should define height of block here
            height = None

          # creating new activity instance
          activity = BasicActivity(title=title, name=name, object=object,
                                   url=url, absolute_begin=block_begin,
                                   absolute_end=block_end,
                                   absolute_start=block_start,
                                   absolute_stop=block_stop, height = height,
                                   color=current_color, info_dict=info,
                                   error=error,
                                   property_dict=self.property_dict)


          # adding new activity to personal group activity list
          try:
            self.basic_activity_list.append(activity)
          except (AttributeError):
            self.basic_activity_list = []
            self.basic_activity_list.append(activity)
          # incrementing indic used for differenciating activities in the same 
          # group (used for Activity naming)
          indic += 1



    else:
      # specific color script
      color_script = getattr(self.object.getObject(),
                             self.field.get_value('color_script'),None)
      # calling color script if exists to set up activity_color
      current_color=''
      if color_script !=None:
        current_color = color_script(self.object.getObject())

      # getting begin and end values from previously recovered method
      if object_property_begin !=None:
        block_begin = \
                    self.object.getObject().getProperty(object_property_begin)
      else:
        block_begin = None

      if object_property_end != None:
        block_end = self.object.getObject().getProperty(object_property_end)
      else:
        block_end = None

      # testing if activity is visible according to the current zoom selection
      # over the secondary_axis
      if block_begin == None:
        block_begin = secondary_axis_info['bound_start']
        current_color='#E4CCE1'
      if block_end == None:
        block_end = secondary_axis_info['bound_stop']
        current_color='#E4CCE1'
      if  (block_begin > secondary_axis_info['bound_stop'] or \
        block_end < secondary_axis_info['bound_start']):
        # activity will not be displayed, stopping process
        pass
      else:
        # activity is somehow displayed. checking if need to cut its bounds
        if block_begin < secondary_axis_info['bound_start']:
          # need to cut begin bound
          block_start = secondary_axis_info['bound_start']
        else: block_start = block_begin

        if block_end > secondary_axis_info['bound_stop']:
          block_stop = secondary_axis_info['bound_stop']
        else:
          block_stop = block_end

        # testing if some activities have errors
        error = 'false'
        if list_error not in (None,[]):
          for activity_error in list_error:
            if activity_error[0][0] == name:
              error = 'true'
              break

        # XXX testing constraint result here.
        # if current object url in list of error constranint urls, then
        # colorizing the block.

        # defining name
        name = "Activity_%s" % (self.object.getObject().getTitle())

        # height should be implemented here
        height = None

        # creating new activity instance
        activity=BasicActivity(title=info['info_center'], name=name,
                               object=self.object.object, url=self.url,
                               absolute_begin=block_begin,
                               absolute_end=block_end,
                               absolute_start=block_start,
                               absolute_stop=block_stop, height=height,
                               color=current_color, info_dict=info,
                               error=error, property_dict=self.property_dict)

        # adding new activity to personal group activity list
        try:
          self.basic_activity_list.append(activity)
        except (AttributeError):
          self.basic_activity_list = []
          self.basic_activity_list.append(activity)



class BasicActivity:
  """ Represents an activity, a task, in the group it belongs to. Beware
      nothing about multitask rendering. """

  def __init__ (self, title='', name='',object = None, url='',
                absolute_begin=None, absolute_end=None, absolute_start=None,
                absolute_stop=None, height=None, constraints='', color=None,
                error='false', info_dict= None, property_dict = {}):
    self.title = title
    self.name = name
    self.object = object
    self.url = url
    self.absolute_begin = absolute_begin # absolute values independant of any
                                         # hypothetic zoom
    self.absolute_end = absolute_end
    self.absolute_start = absolute_start
    self.absolute_stop = absolute_stop
    self.height = height
    self.constraints = constraints
    self.color = color
    self.info_dict = info_dict
    self.error = error
    self.property_dict = property_dict # dict containing specific properties




class PlanningStructure:
  """ class aimed to generate the Planning final structure, including :
      - activities with their blocs (so contains Activity structure)
      - Axis informations (contains Axis Structure).
      The zoom properties on secondary axis are applied to this structure.
      """


  def __init__ (self):
    self.main_axis = ''
    self.secondary_axis = ''
    self.content = []
    self.content_delimiters = None


  def build(self,basic_structure=None, field=None, REQUEST=None):
    """
    main procedure for building Planning Structure
    do all the necessary process to construct a full Structure compliant with
    all expectations (axis, zoom, colors, report_tree, multi_lines, etc.).
    From this final structure just need to run a PageTemplate to get an HTML
    output, or any other script to get the Planning result in the format you
    like...
    """
    # recovering render format ('YX' or 'XY')
    self.calendar_view = field.get_value('representation_type')

    # declaring main axis
    self.main_axis = Axis(title='main axis', name='axis',
                     unit='', axis_order=1,axis_group=[])

    # declaring secondary axis
    self.secondary_axis = Axis(title='sec axis', name='axis',
                     unit='', axis_order=2, axis_group=[])

    # linking axis objects to their corresponding accessor, i.e X or Y
    # this allows the planning to be generic.
    if self.calendar_view == 0:
      self.Y = self.main_axis
      self.X = self.secondary_axis
    else:
      self.Y = self.secondary_axis
      self.X = self.main_axis

    # initializing axis properties
    self.X.name = 'axis_x'
    self.Y.name = 'axis_y'


    # recovering secondary_axis_ bounds
    # Used in case of non calendar mode
    self.secondary_axis.start = \
                      basic_structure.secondary_axis_info['bound_start']
    self.secondary_axis.stop = \
                      basic_structure.secondary_axis_info['bound_stop']


    self.main_axis.size =  self.buildGroups(basic_structure=basic_structure)

    # call method to build secondary axis structure
    # need start_bound, stop_bound and number of groups to build
    # used in non calendar mode
    status = self.buildSecondaryAxis(basic_structure,field)
    if status != 1:
      # ERROR while building secondary axis
      return status
    # completing axisgroup informations according to their bounds
    status = self.completeAxis()
    if status != 1:
      # ERROR while completing axis
      return status
    # the whole structure is almost completed : axis_groups are defined, as
    # axis_elements with their activities. Just need to create blocks related
    # to the activities (special process only for Calendar mode) with their
    # BlockPosition
    status = self.buildBlocs(basic_structure=basic_structure, REQUEST = REQUEST)
    if status != 1:
      # ERROR while building blocks
      return status
    # everything is fine, returning 'true' flag.
    return 1


  def buildSecondaryAxis(self,basic_structure, field):
    """
    build secondary axis structure
    """

    # defining min and max delimiter number
    delimiter_min_number = basic_structure.field.get_value('delimiter')
    if basic_structure.calendar_mode:
      axis_start = 1
      axis_stop = basic_structure.calendar_range + 1
    else:
      axis_stop = (self.secondary_axis.stop)
      axis_start = (self.secondary_axis.start)


    axis_script=getattr(basic_structure.here,
                       basic_structure.field.get_value('sec_axis_script'),None)
    if axis_script == None:
      # ERROR
      message = 'unable to find secondary axis generation script : "%s" does \
             not exist' % basic_structure.field.get_value('sec_axis_script')
      return [(Message(domain=None, message=message, mapping=None))]

    # calling script to get list of delimiters to implement
    # just need to pass start, stop, and the minimum number of delimiter
    # wanted. a structure is returned : list of delimiters, each delimiter
    # defined by a list [ relative position, title, tooltip , delimiter_type]
    try:
      delimiter_list = axis_script(axis_start,axis_stop,delimiter_min_number)
    except (ArithmeticError, LookupError, AttributeError, TypeError):
      message =  'error raised in secondary axis generation script : please \
             check "%s"'% basic_structure.field.get_value('sec_axis_script')
      return [(Message(domain=None, message=message,mapping=None))]

    axis_stop = int(axis_stop)
    axis_start = int(axis_start)
    axis_range = axis_stop - axis_start

    # axis_element_number is used to fix the group size
    self.secondary_axis.axis_size = axis_range
    # axis_group_number is used to differenciate groups
    axis_group_number = 0
    # now iterating list of delimiters and building group list
    # group position and size informations are saved in position_secondary
    # using relative coordinates
    for delimiter in delimiter_list:
      axis_group = AxisGroup(name='Group_sec_' + str(axis_group_number),
                             title=delimiter[1], delimiter_type=delimiter[3])
      axis_group.tooltip = delimiter[2]
      axis_group.position_secondary.relative_begin = \
                             int(delimiter[0]) - int(axis_start)
      # set defaut stop bound and size
      axis_group.position_secondary.relative_end  = int(axis_stop)
      axis_group.position_secondary.relative_range = \
                             int(axis_stop) - int(delimiter[0])
      if delimiter == delimiter_list[0]:
        # actual delimiter is the first delimiter entered
        # do not need to update previous delimiter informations
        pass
      else:
        # actual delimiter info has a previous delimiter
        # update its informations
        self.secondary_axis.axis_group[-1].position_secondary.relative_end = \
          axis_group.position_secondary.relative_begin
        self.secondary_axis.axis_group[-1].position_secondary.relative_range =\
          axis_group.position_secondary.relative_begin - \
          self.secondary_axis.axis_group[-1].position_secondary.relative_begin
      # add current axis_group to axis_group list
      self.secondary_axis.axis_group.append(axis_group)
      axis_group_number += 1

    return 1



  def completeAxis (self):
    """
    complete axis infomations (and more precisely axis position objects) thanks
    to the actual planning structure
    """

    # processing main axis
    for axis_group_element in self.main_axis.axis_group:
      axis_group_element.position_main.absolute_begin = (
              float(axis_group_element.axis_element_start - 1) /
              float(self.main_axis.size))
      axis_group_element.position_main.absolute_end = (
              float(axis_group_element.axis_element_stop) /
              float(self.main_axis.size))
      axis_group_element.position_main.absolute_range = (
              float(axis_group_element.axis_element_number) /
              float(self.main_axis.size))
      axis_group_element.position_secondary.absolute_begin = 0
      axis_group_element.position_secondary.absolute_end = 1
      axis_group_element.position_secondary.absolute_range= 1


    for axis_group_element in self.secondary_axis.axis_group:
      position = axis_group_element.position_secondary
      axis_group_element.position_secondary.absolute_begin = (
           float(axis_group_element.position_secondary.relative_begin) /
           self.secondary_axis.axis_size)
      axis_group_element.position_secondary.absolute_end = (
           float(axis_group_element.position_secondary.relative_end) /
           self.secondary_axis.axis_size)
      axis_group_element.position_secondary.absolute_range = (
           float(axis_group_element.position_secondary.relative_range) /
           self.secondary_axis.axis_size)
      axis_group_element.position_main.absolute_begin = 0
      axis_group_element.position_main.absolute_end   = 1
      axis_group_element.position_main.absolute_range = 1

    # returning 'true' flag at the end of the process
    return 1



  def buildGroups (self, basic_structure=None):
    """
    build groups from activities saved in the structure groups.
    """
    axis_group_number = 0
    axis_element_already_present=0
    for basic_group_object in basic_structure.basic_group_list:
      axis_group_number += 1
      if basic_structure.calendar_mode == 1:
        secondary_axis_range = basic_structure.calendar_range
      else:
        secondary_axis_range = None
      axis_group= AxisGroup(name='Group_' + str(axis_group_number),
                            title=basic_group_object.title,
                            object=basic_group_object.object,
                            axis_group_number = axis_group_number,
                            is_open=basic_group_object.is_open,
                            is_pure_summary=basic_group_object.is_pure_summary,
                            url = basic_group_object.url,
                            depth=basic_group_object.depth,
                            secondary_axis_start = basic_group_object.secondary_axis_start,
                            secondary_axis_stop  = basic_group_object.secondary_axis_stop,
                            secondary_axis_range = secondary_axis_range,
                            property_dict = basic_group_object.property_dict)
      if self.calendar_view == 0:
        axis_group.position_y = axis_group.position_main
        axis_group.position_x = axis_group.position_secondary
      else:
        axis_group.position_y = axis_group.position_secondary
        axis_group.position_x = axis_group.position_main
      # init absolute position over the axis
      axis_group.position_secondary.absolute_begin = 0
      axis_group.position_secondary.absolute_end= 1
      axis_group.position_secondary.absolute_range = 1
      # updating axis_group properties
      axis_group.fixProperties(form_id = basic_structure.form.id,
                               selection_name = basic_structure.selection_name)
      # updating start value
      axis_group.axis_element_start = axis_element_already_present + 1
      activity_number = 0
      if basic_group_object.basic_activity_list != None:
        # need to check if activity list is not empty : possible in case zoom
        # selection is used over the secondary axis
        if axis_group.property_dict['stat'] == 0:
          # case group is task group. Using default method that
          # generates automatically the necessary axis elements
          for basic_activity_object in basic_group_object.basic_activity_list:
            activity_number += 1
            # create new activity in the PlanningStructure
            activity=Activity(name='Group_%s_Activity_%s' %(
                                            str(axis_group_number),
                                            str(activity_number)),
                              title=basic_activity_object.title,
                              object=basic_activity_object.object,
                              color=basic_activity_object.color,
                              link=basic_activity_object.url,
                              secondary_axis_begin= \
                                          basic_activity_object.absolute_begin,
                              secondary_axis_end= \
                                          basic_activity_object.absolute_end,
                              secondary_axis_start= \
                                          basic_activity_object.absolute_start,
                              secondary_axis_stop= \
                                          basic_activity_object.absolute_stop,
                              primary_axis_block=self,
                              info=basic_activity_object.info_dict,
                              calendar_view=self.calendar_view,
                              property_dict=basic_group_object.property_dict)
            # adding activity to the current group
            axis_group.addActivity(activity,axis_element_already_present)
        else:
          # case group is stat group. Using special method that prevent
          # from generating more than 1 axis element and divide tasks size if
          # necessary
          axis_group.addStatActivities(
               basic_activity_list=basic_group_object.basic_activity_list,
               axis_group_number=axis_group_number,
               axis_element_already_present=axis_element_already_present,
               calendar_view=self.calendar_view, primary_axis_block=self,
               property_dict=basic_group_object.property_dict)
      else:
        # basic_activity_list is empty : need to add a empty axis_element to
        # prevent bug or crash
        axis_group.axis_element_number = 1
        new_axis_element=AxisElement(name='Group_%s_AxisElement_1' %
                                           str(axis_group_number),
                                 relative_number= 1,
                                 absolute_number=axis_group.axis_element_start,
                                 parent_axis_group=axis_group)
        # add new activity to this brand new axis_element
        new_axis_element.activity_list = []
        axis_group.axis_element_list = []
        axis_group.axis_element_list.append(new_axis_element)

      axis_group.axis_element_stop = (axis_element_already_present +
                                     axis_group.axis_element_number)
      axis_element_already_present = axis_group.axis_element_stop
      try:
        self.main_axis.axis_group.append(axis_group)
      except AttributeError:
        self.main_axis.axis_group = []
        self.main_axis.axis_group.append(axis_group)
    return axis_element_already_present


  def buildBlocs(self,basic_structure=None, REQUEST=None):
    """
    iterate the whole planning structure to get various activities and build
    their related blocs.
    """
    # recover activity and block error lists
    warning_activity_list = REQUEST.get('warning_activity_list',[])
    error_block_list = REQUEST.get('error_block_list',[])
    error_info_dict = REQUEST.get('error_info_dict',{})
    #pdb.set_trace()
    for axis_group_object in self.main_axis.axis_group:
      for axis_element_object in axis_group_object.axis_element_list:
        for activity in axis_element_object.activity_list:
          # test if activity in warning_activity_list
          if activity.name in warning_activity_list:
            warning = 1
          else:
            warning = 0
          if basic_structure.calendar_mode == 1:
            axis_range = axis_group_object.secondary_axis_range
            axis_start = axis_group_object.secondary_axis_start
            axis_stop  = axis_group_object.secondary_axis_stop
          else:
            axis_start = basic_structure.secondary_axis_info['bound_start']
            axis_stop  = basic_structure.secondary_axis_info['bound_stop']
            axis_range = axis_stop - axis_start
          status = activity.addBlocs(main_axis_start=0,
                                main_axis_stop=self.main_axis.size,
                                secondary_axis_start = axis_start,
                                secondary_axis_stop  = axis_stop,
                                secondary_axis_range = axis_range,
                                planning=self, warning=warning,
                                error_block_list=error_block_list,
                                error_info_dict=error_info_dict)
          if status !=1: return status
        if axis_group_object.property_dict['stat'] == 1:
          # case stat group_object, need to update block size to display
          # stats informations
          status = axis_group_object.updateStatBlocks()
          if status !=1: return status
    # no problem during process, returning 'true' flag
    return 1


class Activity:
  """
  Class representing a task in the Planning, for example an appointment or
  a duration. Can be divided in several blocs for being rendered correctly
  (contains Bloc Structure).
  Activity instance are not rendered but only their blocs. This Activity
  structure is used for rebuilding tasks from bloc positions when
  validating the Planning.
  """
  def __init__ (self,name=None, title=None, object=None, types=None,
                color=None, link=None, height=None, secondary_axis_begin=None,
                secondary_axis_end=None, secondary_axis_start=None,
                secondary_axis_stop=None, primary_axis_block=None, info=None,
                calendar_view=0, property_dict={} ):
    self.name = name # internal activity_name
    self.id = self.name
    self.title = title # displayed activity_name
    self.object = object
    self.types = types # activity, activity_error, info
    self.color = color # color used to render all Blocs
    self.link = link # link to the ERP5 object
    self.height = height
    # self.constraints = constraints
    self.block_list = None # contains all the blocs used to render the activity
    self.secondary_axis_begin =secondary_axis_begin
    self.secondary_axis_end=secondary_axis_end
    self.secondary_axis_start=secondary_axis_start
    self.secondary_axis_stop=secondary_axis_stop
    self.primary_axis_block = primary_axis_block
    self.block_bounds = None
    self.info = info
    self.parent_axis_element = None
    self.calendar_view= calendar_view
    self.property_dict = property_dict


  def get_error_message (self, Error):
    # need to update the error message
    return 'task %s (%s)not validated' % (self.name, self.title)


  def isValidPosition(self, bound_begin, bound_end):
    """
    can check if actual activity can fit within the bounds, returns :
    - 0 if not
    - 1 if partially ( need to cut the activity bounds to make it fit)
    - 2 definitely
    """
    if (self.secondary_axis_begin > bound_end) or \
       (self.secondary_axis_end < bound_begin):
      return 0
    elif (self.secondary_axis_begin > bound_begin) and \
         (self.secondary_axis_end < bound_end):
      return 1
    else:
      return 2


  def addBlocs(self, main_axis_start=None, main_axis_stop=None,
               secondary_axis_start=None, secondary_axis_stop=None,
               secondary_axis_range=None, planning=None, warning=0,
               error_block_list=[], error_info_dict={}):
    """
    define list of (begin & stop) values for blocs representing the actual
    activity (can have several blocs if necessary).
    """
    # recover list of bounds
    if self.secondary_axis_start != None or self.secondary_axis_stop != None:
      #split_method_name = field.get_value('split_method',None)
      #split_method = getattr(self.object,split_method_name, None)
      #if split_method != None:

      secondary_block_bounds = self.splitActivity()
      #secondary_block_bounds = split_method(self.secondary_axis_start,
                                           # self.secondary_axis_stop)

    else:
       secondary_block_bounds = \
          [[secondary_axis_start, secondary_axis_stop,1]]

    block_number = 0
    # iterating resulting list
    for (start,stop,zone) in secondary_block_bounds:

      block_number += 1

      block_name = self.name + '_Block_' + str(block_number)
      # create new block instance

      if block_name in error_block_list:
        error = 1
        error_text= error_info_dict[block_name]
      else:
        error = 0
        error_text=''

      # zone property is used to check if block is an active (main activity
      # block) block or a passive one (just a display block)
      if zone == 1:
        # active
        block_color = self.color
        block_link = self.link
      else:
        # passive
        block_color = '#D1E8FF'
        block_link = ''

      new_block = Bloc(name= block_name,color=block_color,link=block_link,
                       number = block_number,
                       calendar_view=self.calendar_view, parent_activity=self,
                       warning=warning, error=error,
                       error_text=error_text,zone=zone,
                       property_dict=self.property_dict)

      new_block.buildInfoDict(info_dict = self.info)

      # updating secondary_axis block position
      if self.secondary_axis_start != None:
        new_block.position_secondary.absolute_begin = start
      else:
        new_block.position_secondary.absolute_begin = secondary_axis_start
      if self.secondary_axis_stop != None:
        new_block.position_secondary.absolute_end = stop
      else:
        new_block.position_secondary.absolute_end = secondary_axis_stop
      new_block.position_secondary.absolute_range = stop - start
      # updating main_axis block position
      new_block.position_main.absolute_begin = \
                      self.parent_axis_element.absolute_number - 1
      new_block.position_main.absolute_end = \
                      self.parent_axis_element.absolute_number
      new_block.position_main.absolute_range = (
                      new_block.position_main.absolute_end -
                      new_block.position_main.absolute_begin)

      # now absolute positions are updated, and the axis values are known
      # (as parameters), processing relative values
      # => but before updating secondary_axis bounds
      #pdb.set_trace()
      new_block.position_secondary.relative_begin = (
          float(new_block.position_secondary.absolute_begin -
          secondary_axis_start) / float(secondary_axis_range))
      new_block.position_secondary.relative_end = (
          float(new_block.position_secondary.absolute_end -
          secondary_axis_start) / float(secondary_axis_range))
      new_block.position_secondary.relative_range = (
          new_block.position_secondary.relative_end -
          new_block.position_secondary.relative_begin)

      """
      new_block.position_secondary.relative_begin = (
          float(new_block.position_secondary.absolute_begin -
          secondary_axis_start) / float(secondary_axis_stop -
          secondary_axis_start))
      new_block.position_secondary.relative_end = (
          float(new_block.position_secondary.absolute_end -
          secondary_axis_start) / float(secondary_axis_stop -
          secondary_axis_start))
      new_block.position_secondary.relative_range = (
          new_block.position_secondary.relative_end -
          new_block.position_secondary.relative_begin)
      """

      new_block.position_main.relative_begin = (
          float(new_block.position_main.absolute_begin - main_axis_start) /
          float(main_axis_stop - main_axis_start))
      new_block.position_main.relative_end = (
          float(new_block.position_main.absolute_end - main_axis_start) /
          float(main_axis_stop - main_axis_start))
      new_block.position_main.relative_range = (
          new_block.position_main.relative_end -
          new_block.position_main.relative_begin)

      try:
        self.block_list.append(new_block)
      except AttributeError:
        # in case this is the first add 
        # need to initialize the list
        self.block_list = []
        self.block_list.append(new_block)

      try:
        planning.content.append(new_block)
      except AttributeError:
        planning.content = []
        planning.content.append(new_block)

    return 1

  def splitActivity(self):
    """
    Used for splitting an activity in multiple bloc.
    [EDIT] will not be used to split Calendar axis (by date time depending on
           the axis size), but will certainly be used afterwards in all cases
           to split activity in multiple blocs according to some external
           constraints (do not work sat & sun, or for a dayly planning do not
           work from 18P.M to 9A.M).
           will use an external script to do so.
    """
    # XXX not implemented yet
    return [(self.secondary_axis_start,self.secondary_axis_stop,1)]

    returned_list = []


    start_date = self.secondary_axis_start
    stop_date = self.secondary_axis_stop

    temp_start = start_date
    temp_stop  = temp_start

    # defining usefull list of data
    break_list = ['Saturday','Sunday']
    worked_list = ['Monday','Tuesday','Wednesday','Thursday','Friday']

    if temp_start.Day() in break_list:
      # temp_start is in weekend,
      # getting first worked day
      while temp_start.Day() in break_list and temp_start < stop_date:
        temp_start += 1
      returned_list.append([temp_stop,temp_start,0])
    else:
      # temp_stop is in week, getting first weekend
      while temp_stop.Day() in worked_list and temp_stop < stop_date:
        temp_stop += 1
      if temp_stop > stop_date:
        temp_stop = stop_date

    # testing if current activity is not too small to create blocks
    while temp_start < stop_date:
      returned_list.append([temp_start,temp_stop,1])

      temp_start = temp_stop
      # going to next start_date
      while temp_start.Day() in break_list and temp_start < stop_date:
        temp_start += 1

      # adding new start date to list
      if temp_start >= stop_date:
        returned_list.append([temp_stop,stop_date,0])
      elif temp_start != temp_stop:
        returned_list.append([temp_stop,temp_start,0])
      # next temp_start has been found
      # now processing new temp_stop
      temp_stop = temp_start
      while temp_stop.Day() in worked_list and temp_stop < stop_date:
        temp_stop += 1
      if temp_stop > stop_date:
        temp_stop = stop_date

    # return new list
    return returned_list



class Bloc:
  """
  structure that will be rendered as a bloc, a task element.
  Blocs are referenced in the Activity they belong to (logical structure), but
  are also referenced in their relative AxisElement (to be able to calculate
  the number of lines required for rendering when having multi-tasking in
  parallel).
  Contains Bloc Structure for position informations.
  """

  def __init__ (self, name=None, types=None,
                color=None, info=None, link=None, number=0,
                constraints=None, secondary_start=None, secondary_stop=None,
                calendar_view=0, parent_activity = None, warning=0, error=0,
                error_text='', zone=1, property_dict ={} ):
    """
    creates a Bloc object
    """
    self.name = name # internal name
    self.types = types # activity, activity_error, info
    self.color = color
    self.info = info # dict containing text with their position
    self.link = link # on clic link
    self.number = number
    self.title=''
    self.zone = zone # 1 = usefull area : 0 = useless one
    self.parent_activity = parent_activity
    self.constraints = constraints
    # setting warning and error flags in case parent_activity or block itself
    # have not been validated
    self.warning = warning
    self.error = error
    self.error_text = error_text
    # list of all the groups the bloc belongs to (reportTree)
    #self.container_axis_group = container_AxisGroup
    # integer pointing to the AxisElement containing the bloc (multitasking)
    #self.container_axis_element = container_AxisElement
    self.position_main = Position()
    self.position_secondary = \
          Position(absolute_begin=secondary_start,absolute_end=secondary_stop)
    if calendar_view == 0:
      self.position_y = self.position_main
      self.position_x = self.position_secondary
    else:
      self.position_y = self.position_secondary
      self.position_x = self.position_main
    self.render_dict = None
    self.property_dict = property_dict # dict containing internal properties

  def buildInfoDict (self, info_dict=[]):
    """
    create Info objects to display text & images, then link them to the
    current object
    """

    # updating title
    if self.property_dict['stat'] == 1:
      self.title = str(self.parent_activity.height)
      self.info = None
    else:
      self.info = {}
      title_list = []
      title_list.append(
                 self.buildInfo(info_dict=info_dict, area='info_topleft'))
      title_list.append(
                 self.buildInfo(info_dict=info_dict, area='info_topright'))
      title_list.append(
                 self.buildInfo(info_dict=info_dict, area='info_center'))
      title_list.append(
                 self.buildInfo(info_dict=info_dict, area='info_botleft'))
      title_list.append(
                 self.buildInfo(info_dict=info_dict, area='info_botright'))
      self.title = " | ".join(title_list)


    if self.error != 0:
      # field has error
      # adding text_error
      self.info['info_error'] = Info(info=self.error_text, link='')

  def buildInfo(self,info_dict=[],area=None):
    if area in info_dict:
      # creating new object
      info = Info(info = info_dict[area], link = self.link)
      # saving new object to block dict
      self.info[area] = info
      # recovering text information
      return info_dict[area]
    else:
      return ''

class Position:
  """
  gives a bloc [/or an area] informations about it's position on the X or Y
  axis. can specify position in every kind of axis : continuous or listed
  with lower and upper bound.
  """

  def __init__ (self, absolute_begin=None, absolute_end=None,
                absolute_range=None, relative_begin=None, relative_end=None,
                relative_range=None):
    # absolute size takes the bloc size in the original unit for the axis
    self.absolute_begin = absolute_begin
    self.absolute_end = absolute_end
    self.absolute_range = absolute_range
    # selative size in % of the current axis size
    self.relative_begin = relative_begin
    self.relative_end = relative_end
    self.relative_range = relative_range


class Axis:
  """
  Structure holding informations about a specified axis.Can be X or Y axis.
  Is aimed to handle axis with any kind of unit : continuous or listed (
  including possibly a listed ReportTree).
  Two of them are needed in a PlanningStructure to have X and Y axis.
  In case of listed axis, holds AxisGroup Structure.
  """

  def __init__(self, title=None, unit=None, types=None, axis_order=None,
               name=None, axis_group=None):
    self.title = title # axis title
    self.unit = unit # unit kind (time, nb... person, task, etc.)
    self.types = types # continuous / listed (incl. ReportTree)
    self.name = name
    self.size = 0 # value
    # axis group is a single group that contain the axis structure.
    # defined to be able to use a generic and recursive method to 
    self.axis_group = axis_group
    # specify if axis is primary or secondary.
    # - if primary axis in Planning, zoom selection is applied thanks to 
    # a cut over the basic structure objects (based on their position and
    # their length).
    # - if secondary axis in Planning, then need to apply the second zoom
    # bounds (application will be based on two bounds : start & stop)
    self.axis_order = axis_order
    # dict containing all class properties with their values
    self.render_dict=None


class AxisGroup:
  """
  Class representing an item, that can have the following properties :
  - one or several rendered lines (multiTasking) : contains AxisElement
  structure to hold this.
  - one or several sub groups (ReportTree) : contains AxisGroup structure
  to hold sub groups elements.
  """

  def __init__ (self, name='', title='', object = None,
                axis_group_list=None, axis_group_number=0,
                axis_element_list=None, axis_element_number=0,
                delimiter_type=0, is_open=0, is_pure_summary=1,depth=0,
                url=None, axis_element_already_insered= 0,
                secondary_axis_start=None, secondary_axis_stop=None,
                secondary_axis_range=None,
                property_dict={}):
    self.name = name
    self.title = title
    self.link = None # link to fold or unfold report in report-tree mode
    self.info_title = Info(info=self.title, link=self.link, title=self.title)
    self.tooltip = '' # tooltip used when cursor pass over the group
    self.object = object # ZODB object used to validate modifications
    self.axis_group_list = axis_group_list # ReportTree
    self.axis_group_number = axis_group_number
    self.axis_element_list = axis_element_list # Multitasking
    self.axis_element_number = axis_element_number
    self.axis_element_start = None
    self.axis_element_stop = None
    self.delimiter_type = delimiter_type
    # define the kind of separator used in graphic rendering
    # 0 for standard, 1 for bold, 2 for 2x bold
    # dict containing all class properties with their values
    self.render_dict=None
    self.is_open = is_open
    self.is_pure_summary = is_pure_summary
    self.depth = depth
    self.url = url # url to the object

    self.position_main = Position()
    self.position_secondary = Position()
    self.position_x = None
    self.position_y = None
    # secondary_axis_bounds are specified for each axis_group to handle
    # calendar view.
    self.secondary_axis_start = secondary_axis_start
    self.secondary_axis_stop = secondary_axis_stop
    # secondary_axis_range is used in calendar mode to define range of the
    # largest axis. In case of month calendar, range is 31 so that even
    # tasks on febuary will be positioned over 31 days (and not 28) so that all
    # groups matches the same scale.
    self.secondary_axis_range = secondary_axis_range
    self.property_dict = property_dict


  security = ClassSecurityInfo()
  security.declarePublic('setTitle')
  def setTitle(self,new_title = None):
    self.title = new_title

  def fixProperties(self, form_id=None, selection_name=None):
    """
    using actual AxisGroup properties to define some special comportement that
    the axisGroup should have, especially in case of report-tree
    """
    if self.is_open:
      # current report is unfold, action 'fold'
      self.info_title.link = 'portal_selections/foldReport?report_url=' + \
                              '%s&form_id=%s&list_selection_name=%s' %(
                              self.url, form_id, selection_name)
      self.info_title.info = '[-] ' + self.info_title.info
    else:
      # current report is fold, action 'unfold'
      self.info_title.link = 'portal_selections/unfoldReport?report_url=' + \
                             '%s&form_id=%s&list_selection_name=%s' %(
                              self.url, form_id, selection_name)
      self.info_title.info = '[+] ' + self.info_title.info

    #for i in range(self.depth):
    #  self.title = '| ' + self.title
    self.info_title.title = self.info_title.info

    self.tooltip = self.info_title.info


  def addActivity(self, activity=None, axis_element_already_insered= 0):
    """
    procedure that permits to add activity to the corresponding AxisElement in
    an AxisGroup. can create new Axis Element in the actual Axisgroup if
    necessary. Permits representation of MULTITASKING
    """

    # declaring variable used to check if activity has already been added
    added = 0
    try:
      # iterating each axis_element of the axis_group
      for axis_element in self.axis_element_list:

        can_add = 1
        # recovering all activity properties of the actual axis_element and
        # iterating through them to check if one of them crosses the new one
        for activity_statement in axis_element.activity_list:

          if activity_statement.isValidPosition(activity.secondary_axis_begin,
                                             activity.secondary_axis_end) != 0:
            # isValidPosition returned 1 or 2, this means the activity already
            # present does prevent from adding the new activity as there is
            # coverage on the current axis_element.
            # stop iterating actual axis_element and try with the next one
            can_add = 0
            break

        if can_add:
          # the whole activity_statements in actual axis have been succesfully
          # tested without problem.
          # can add new activity to the actual axis_element
          added = 1
          axis_element.activity_list.append(activity)

          # updating activity properties
          activity.parent_axis_element = axis_element

          # no need to check the next axis_elements to know if they can hold
          # the new activity as it is already added to an axis_element
          break

      if not added:
        # all axis_elements of the current group have been tested and no one
        # can contain the new activity.
        self.axis_element_number += 1
        # Need to create a new axis_element to hold the new activity
        new_axis_element=AxisElement(name='Group_%s_AxisElement_%s'%
                                          (str(self.axis_group_number),
                                           str(self.axis_element_number)),
                                     relative_number=self.axis_element_number,
                                     absolute_number=self.axis_element_number+
                                              axis_element_already_insered)

        # add new activity to this brand new axis_element
        new_axis_element.activity_list = []
        new_axis_element.activity_list.append(activity)

        # updating activity properties
        activity.parent_axis_element = new_axis_element

        # register the axis_element to the actual group.
        self.axis_element_list.append(new_axis_element)
    except TypeError:
      # in case axis_element_list is Empty (first activity to the group)
      # Need to create a new axis_element to hold the new activity
      self.axis_element_number += 1
      new_axis_element = AxisElement(name='Group_%s_AxisElement_1' %
                                           str(self.axis_group_number),
                                     relative_number=\
                                           self.axis_element_number,
                                     absolute_number =\
                                           axis_element_already_insered +
                                           self.axis_element_number,
                                     parent_axis_group=self)

      # add new activity to this brand new axis_element
      new_axis_element.activity_list = []
      new_axis_element.activity_list.append(activity)

      # updating activity properties
      activity.parent_axis_element = new_axis_element

      # register the axis_element to the actual group.
      self.axis_element_list = []
      self.axis_element_list.append(new_axis_element)


  def addStatActivities(self, basic_activity_list=None, axis_group_number=0,
                        axis_element_already_present= 0, calendar_view=0,
                        primary_axis_block=None, property_dict={}):
    """
    Permits to add stat block to the current AxisGroup. In this way use the
    single AxisElement present to fit the blocks
    """
    # first adding axis_element to the current group
    self.axis_element_number += 1
    new_axis_element=AxisElement(name='Group_%s_AxisElement_1' %
                                       str(self.axis_group_number),
                                 relative_number=self.axis_element_number,
                                 absolute_number=axis_element_already_present+
                                                 self.axis_element_number,
                                 parent_axis_group=self)
    new_axis_element.activity_list = []

    self.axis_element_list = []
    self.axis_element_list.append(new_axis_element)

    activity_number = 0
    # add all activities to the same axis_element
    for basic_activity_object in basic_activity_list:

      # defining Activity from basic_activity_object
      activity = Activity(name= 'Group_%s_Activity_%s' 
                               %(str(axis_group_number),
                                 str(activity_number)),
                          title=basic_activity_object.title,
                          object=basic_activity_object.object,
                          color=basic_activity_object.color,
                          link=basic_activity_object.url,
                          secondary_axis_begin=\
                                 basic_activity_object.absolute_begin,
                          secondary_axis_end=\
                                 basic_activity_object.absolute_end,
                          secondary_axis_start=\
                                 basic_activity_object.absolute_start,
                          secondary_axis_stop=\
                                 basic_activity_object.absolute_stop,
                          height=basic_activity_object.height,
                          primary_axis_block=primary_axis_block,
                          info=basic_activity_object.info_dict,
                          calendar_view=calendar_view,
                          property_dict = property_dict)
      activity.parent_axis_element = new_axis_element

      # append activity to current axis_element
      new_axis_element.activity_list.append(activity)

      activity_number +=1


  def updateStatBlocks(self):
    """
    called once the blocks have been defined on all activities
    if the current group is  stat group, then this method is called
    process :
      - find the largest element to display
      - update size of all other elements
    """
    # usually should get only 1 axis_element : all stats are displayed on the
    # same line.
    max_activity_height = 0
    for activity in self.axis_element_list[0].activity_list:
      if activity.height > max_activity_height:
        max_activity_height = activity.height

    # now max height is known, just need to adapt size of all the blocks
    # composing the activities
    for activity in self.axis_element_list[0].activity_list:
      if activity.height in (0,None):
        relative_size = 1
      else:
        relative_size = float(activity.height) / max_activity_height
      for block in activity.block_list:
        # recovering original values
        block_range = block.position_main.relative_range
        block_begin = block.position_main.relative_begin
        block_end   = block.position_main.relative_end
        # calculating values
        final_range = relative_size * block_range
        final_loss = block_range - final_range
        final_begin = block_begin + final_loss
        # saving new values
        block.position_main.relative_begin = final_begin
        block.position_main.relative_range = final_range
    return 1


class AxisElement:
  """
  Represents a line in an item. In most cases, an AxisGroup element will
  hold ony one AxisElement (simple listed axis), but sometimes more
  AxisElements are required (multi, simultaneous tasking).
  AxisElement is linked with the blocs displayed in it : this is only
  usefull when doing multitasking to check if a new bloc can be added to an
  existing AxisElement or if it is needed to create a new AxisElement in
  the AxisGroup to hold it.
  """
  def __init__ (self,name='', relative_number=0, absolute_number=0,
                activity_list=None, parent_axis_group = None):
    self.name = name
    self.relative_number = relative_number # relative number / AxisGroup
    self.absolute_number = absolute_number # id in the current rendering
    self.activity_list = activity_list
    # dict containing all class properties with their values
    self.render_dict=None
    self.parent_axis_group = parent_axis_group


class Info:
  """
  Class holding all informations to display an info text div inside of a block
  or AxisGroup or whatever
  """
  security = ClassSecurityInfo()
  def __init__(self, info=None, link=None, title=None):
    self.info = info
    self.link = link
    self.title = title

  security.declarePublic('edit')
  def edit(self, info=None):
     """
     special method allowing to update Info content from an external script
     """
     self.info = info

# declaring validator instance
PlanningBoxValidatorInstance = PlanningBoxValidator()

class PlanningBox(ZMIField):
    meta_type = "PlanningBox"
    widget = PlanningBoxWidgetInstance
    validator = PlanningBoxValidatorInstance
    security = ClassSecurityInfo()
    security.declareProtected('Access contents information', 'get_value')
    def get_value(self, id, **kw):
      if id == 'default' and kw.get('render_format') in ('list', ):
        return self.widget.render(self, self.generate_field_key() , None , 
                                  kw.get('REQUEST'),
                                  render_format=kw.get('render_format'))
      else:
        return ZMIField.get_value(self, id, **kw)

    def render_css(self, value=None, REQUEST=None):
      return self.widget.render_css(self,'',value,REQUEST)


InitializeClass(PlanningBoxWidget)
allow_class(PlanningBoxWidget)
InitializeClass(BasicStructure)
allow_class(BasicStructure)
InitializeClass(BasicGroup)
allow_class(BasicGroup)
InitializeClass(BasicActivity)
allow_class(BasicActivity)
InitializeClass(PlanningStructure)
allow_class(PlanningStructure)
InitializeClass(Activity)
allow_class(Activity)
InitializeClass(Bloc)
allow_class(Bloc)
InitializeClass(Position)
allow_class(Position)
InitializeClass(Axis)
allow_class(Axis)
InitializeClass(AxisGroup)
allow_class(AxisGroup)
InitializeClass(AxisElement)
allow_class(AxisElement)
InitializeClass(Info)
allow_class(Info)



