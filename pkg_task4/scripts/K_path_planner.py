#!/usr/bin/env python

import rospy
import math
from sensor_msgs.msg import NavSatFix, LaserScan, Imu
from vitarana_drone.srv import *
from std_msgs.msg import String
import csv
import os

class PathPlanner():

    def __init__(self):
        rospy.init_node('path_planner_beta')

        # Destination to be reached
        # [latitude, longitude, altitude]
        self.destination = None  # will contain single destination to reach
        self.destination_list = []  # will contain all the destinations
        self.destination = [0, 0, 0]  # for reaching at evry destination
        self.box_list = []  # will contain all the coordinates of the box
        self.drone_coordinates = [0, 0, 0]  # initial coordinates
        # will help to switch the functions between obstacle_avoid and marker_find
        self.function_switch = True
        self.pose_mark_cnt = 0  # for switching the destination in market find
        self.pose_marker_flag = True  # for making sure that previouse movement is done
        # receving marker coordinates from the marker_detect.py
        self.img_data = [0, 0]
        self.next_delevery = 0  # counter for delevering parcel on different buildings
        # will switch the between box_list and drone_coordinates
        self.destination_switch = False
        self.box_reach_flag = False

        self.attech_situation = False
        self.counter_for_initial_pos=0#for taking the drone coordinates from the gps
        self.destination_init()
        # Converting latitude and longitude in meters for calculation
        self.destination_xy = [0, 0]
        
        #edit for opt
        self.take_destination = True                    #shifted thrshould box flag
        self.given_destination=NavSatFix()              #giving destination from the points
        self.points=[0,0,0]                             #for nevigetting
        self.interrupt=False                            #for imergency checkpoint shifting

        # Present Location of the DroneNote
        self.current_location = [0, 0, 0]
        # Converting latitude and longitude in meters for calculation
        self.current_location_xy = [0, 0]

        # The checkpoint node to be reached for reaching final destination
        self.checkpoint = NavSatFix()

        self.desti_data=NavSatFix()

        # Initializing to store data from Lazer Sensors
        self.obs_range_top = []
        # self.obs_range_bottom = []

        # Defining variables which are needed for calculation
        # diffrence of current and final position
        self.diff_xy = [0, 0]
        self.distance_xy = 0                # distance between current and final position

        self.movement_in_1D = 0             # maximum movement to be done in one direction
        # [x, y] -> movement distribution in x and y
        self.movement_in_plane = [0, 0]
        # closest distance of obstacle (in meters)
        self.obs_closest_range = 12

        self.sample_time = 0.01

        # Publisher
        self.pub_checkpoint = rospy.Publisher('/checkpoint', NavSatFix, queue_size=1)
        self.grip_flag=rospy.Publisher('/gripp_flag',String,queue_size=1)
        self.destination_data=rospy.Publisher('/destination_data' , NavSatFix,queue_size=1)
        

        # Subscriber
        rospy.Subscriber('/edrone/gps', NavSatFix, self.gps_callback)
        rospy.Subscriber('/edrone/range_finder_top', LaserScan, self.range_finder_top_callback)
        rospy.Subscriber('/edrone/gripper_check', String, self.gripper_check_callback)
        rospy.Subscriber('/marker_error', NavSatFix, self.marker_error_callback)
        # rospy.Subscriber('/edrone/range_finder_bottom', LaserScan, self.range_finder_bottom_callback)

    # def final_setpoint_callback(self, msg):
    #     self.destination = [msg.latitude, msg.longitude, msg.altitude]


    #edit for opt
    def marker_error_callback(self, msg):
        self.img_data = [msg.latitude, msg.longitude]

    def gripper_check_callback(self, state):
        self.attech_situation = state.data

    def destination_init(self):
        box_list_notations=[]#it will store the grid symbols in the list
        first_grid_lat=18.9999864489
        first_grid_long=71.9999430161
        diff_lat=0.000013552
        diff_long=0.000014245
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),'manifest.csv'),'r') as x:
            content = csv.reader(x)
            #print(content)
            self.iter=0
            for i in content:
                self.destination_list.append(i)
                box_note=self.destination_list[self.iter].pop(0)
                box_note=list(box_note);box_note[1]=int(box_note[1])
                box_list_notations.append(box_note)
                self.iter+=1
        for i in range(len(self.destination_list)):
            for j in range(len(self.destination_list)):
                self.destination_list[i][j]=float(self.destination_list[i][j])
        # print(self.destination_list)
        # while(self.drone_coordinates[2]==0):
        #     continue
        for i in range(len(box_list_notations)):
            x=0
            y=0
            for j in range(len(box_list_notations[i])):
                if(j==0):
                    if(box_list_notations[i][j]=='A'):
                        x=first_grid_lat+0
                    elif(box_list_notations[i][j]=='B'):
                        x=first_grid_lat+diff_lat
                    elif(box_list_notations[i][j]=='C'):
                        x=first_grid_lat+2*diff_lat
                else:
                    if(box_list_notations[i][j]==1):
                        y=first_grid_long+0
                    elif(box_list_notations[i][j]==2):
                        y=first_grid_long+diff_long
                    elif(box_list_notations[i][j]==3):
                        y=first_grid_long+2*diff_lat
            self.box_list.append([x,y,self.drone_coordinates[2]])


    
    def gps_callback(self, msg):
        if(msg.latitude!=0):
            if(self.counter_for_initial_pos==0):
                self.drone_coordinates=[msg.latitude, msg.longitude, msg.altitude]
                print(self.counter_for_initial_pos)
                self.counter_for_initial_pos=self.counter_for_initial_pos+1
            self.current_location = [msg.latitude, msg.longitude, msg.altitude]

    def range_finder_top_callback(self, msg):
        self.obs_range_top = msg.ranges

    # def range_finder_bottom_callback(self, msg):
    #     self.obs_range_bottom = msg.ranges

    # Functions for data conversion between GPS and meter with respect to origin
    def lat_to_x(self, input_latitude): return 110692.0702932625 *(input_latitude - 19)
    def long_to_y(self, input_longitude): return - 105292.0089353767 * (input_longitude - 72)

    def x_to_lat_diff(self, input_x): return (input_x / 110692.0702932625)
    def y_to_long_diff(self, input_y): return (input_y / -105292.0089353767)

    def calculate_movement_in_plane(self, total_movement):
        '''This Function will take the drone in straight line towards destination'''

        # movement in specific direction that is x and y
        specific_movement = [0, 0]

        # Applying symmetric triangle method
        specific_movement[0] = (
            total_movement * self.diff_xy[0]) / self.distance_xy
        specific_movement[1] = (
            total_movement * self.diff_xy[1]) / self.distance_xy
        return specific_movement

    def reset_and_reform(self):
        self.next_delevery+=1
        if self.next_delevery==3:
            self.destination_list.append(self.drone_coordinates)
            self.box_list.append(self.drone_coordinates)
        print(self.next_delevery)
        self.function_switch=True
        self.pose_mark_cnt=0
        self.pose_marker_flag=True
        self.img_data=[0,0]
        self.destination_switch=False
        self.box_reach_flag=False

    def coordinate_switch(self):
        print(self.next_delevery)
        '''it will be very helpful to differentiat boxs and destinations'''
        if(self.next_delevery==3):
            self.destination=self.drone_coordinates
        elif(not self.destination_switch):
            self.destination=self.box_list[self.next_delevery]
        else:
            self.destination=self.destination_list[self.next_delevery]
    
    def destination_check(self):
        ''' function will hendle all desired positions '''
        # Threshould for gripplig the box
        if(-0.000010417 <= (self.box_list[self.next_delevery][0]-self.current_location[0]) <= 0.000010417):
            if (-0.0000037487 <= (self.box_list[self.next_delevery][1]-self.current_location[1])<= 0.0000037487):
                self.box_reach_flag=True
                if(-0.1 <= (self.drone_coordinates[2]-self.current_location[2])<= 0.2 and self.attech_situation=='True'):
                    self.grip_flag.publish('True')
                    # print("box_grip_flag_is_published/publishing")
                    self.box_reach_flag=False
                    self.destination_switch=True

        # Threshould for finding that drone has reached givrn coordinats from csv file
        if -0.000010217 <= (self.destination_list[self.next_delevery][0]-self.current_location[0]) <= 0.000010217:
            if -0.0000037487 <= (self.destination_list[self.next_delevery][1]-self.current_location[1])<= 0.0000037487:
                
                self.function_switch=False

        # Threshould for checking every single checkpoint
        if -0.000010217 <= (self.given_destination.latitude-self.current_location[0]) <= 0.000010217:
            if -0.0000037487 <= (self.given_destination.longitude-self.current_location[1])<= 0.0000037487:
                if (-0.2<= (self.given_destination.altitude-self.current_location[2]) <= 0.2) or self.attech_situation=='True':
                    self.take_destination = True
                    # print(self.take_destination)


    def obstacle_avoid(self):
        '''For Processing the obtained sensor data and publishing required 
        checkpoint for avoiding obstacles'''

        if self.destination == [0, 0, 0]:
            return

        data = self.obs_range_top
        self.movement_in_plane = [0, 0]

        # destination in x and y form
        self.current_location_xy = [self.lat_to_x(self.destination[0]),
                                    self.long_to_y(self.destination[1])]

        self.destination_xy = [self.lat_to_x(self.current_location[0]),
                               self.long_to_y(self.current_location[1])]

        self.diff_xy = [self.destination_xy[0] - self.current_location_xy[0],
                        self.destination_xy[1] - self.current_location_xy[1]]

        self.distance_xy = math.hypot(self.diff_xy[0], self.diff_xy[1])

        # Calculating maximum distance to be covered at once
        # It can be done more efficiently using another pid
        for obs_distance in data:
            if 16 <= obs_distance:
                self.movement_in_1D = 15
            elif 9 <= obs_distance:
                self.movement_in_1D = 4
            else:
                self.movement_in_1D = 2.5

        i = 0; movement = [0, 0, 0, 0, 0]
        for obs_distance in data:
            movement[i] = obs_distance * 0.75
            # if obs_distance < self.obs_closest_range:
            #     movement[i] = obs_distance - self.obs_closest_range
                # This would be negative cause we wanna pull back our drone if it gets too close
            if obs_distance > 25:
                movement[i] = 25
            i+=1

        self.movement_in_plane = [min(movement[0],movement[2]),min(movement[1],movement[3])]
        # checking if destination is nearer than maximum distance to be travelled

        if self.movement_in_1D >= self.distance_xy:
            self.movement_in_1D = self.distance_xy

        # doge the obstacle if its closer than certain distance
        for i in range(len(data)-1):
            if data[i] <= self.obs_closest_range:
                if i % 2 != 0:
                    self.movement_in_plane[0] = data[i] - self.obs_closest_range
                    
                    if(-0.0000107487 <= (self.given_destination.longitude-self.current_location[1])<= 0.0000107487):
                        self.movement_in_plane[1]=12
                    else:
                        self.movement_in_plane[1] = self.movement_in_1D
                    break
            else:
                self.movement_in_plane = self.calculate_movement_in_plane(
                    self.movement_in_1D)
    
        # setting the values to publish
        self.checkpoint.latitude = self.current_location[0] - self.x_to_lat_diff(self.movement_in_plane[0])
        self.checkpoint.longitude = self.current_location[1] - self.y_to_long_diff(self.movement_in_plane[1])
        # giving fixed altitude for now will work on it in future
        if(self.box_reach_flag and self.destination_switch==False):
            self.checkpoint.altitude=self.drone_coordinates[2]-0.2
        elif(self.next_delevery==3):
            self.checkpoint.altitude = self.destination_list[2][2]+3
        else:
            self.checkpoint.altitude = self.destination_list[self.next_delevery][2]+3

        # Publishing
        if(self.take_destination and self.checkpoint.latitude!=0):
            # print(self.take_destination)
            self.points=[self.checkpoint.latitude,self.checkpoint.longitude,self.checkpoint.altitude]
            self.take_destination=not self.take_destination
        [self.given_destination.latitude,self.given_destination.longitude,self.given_destination.altitude]=self.points

        if self.next_delevery <= 2:
            self.pub_checkpoint.publish(self.given_destination)
            self.desti_data.latitude=self.destination_list[self.next_delevery][0]
            self.desti_data.longitude=self.destination_list[self.next_delevery][1]
            self.desti_data.altitude=self.destination_list[self.next_delevery][2]

    def marker_find(self):
        if(self.next_delevery<3):
            if(self.pose_mark_cnt==0):
                self.checkpoint.altitude=self.destination_list[self.next_delevery][2]+10
                self.pose_mark_cnt+=1
                self.pose_marker_flag=False
            if(self.img_data[0]!=0.0 and self.pose_mark_cnt==1 and self.pose_marker_flag==True):
                self.checkpoint.latitude=self.current_location[0]+self.x_to_lat_diff(self.img_data[0])
                self.checkpoint.longitude=self.current_location[1]+self.y_to_long_diff(self.img_data[1])
                self.checkpoint.altitude=self.destination_list[self.next_delevery][2]+4
                self.pose_mark_cnt+=1
                self.pose_marker_flag=False
            if(self.pose_mark_cnt == 2 and self.pose_marker_flag==True):
                self.checkpoint.altitude=self.destination_list[self.next_delevery][2]
                self.pose_mark_cnt+=1
                self.pose_marker_flag=False

            self.pub_checkpoint.publish(self.checkpoint)
            self.destination_data.publish(self.desti_data)

    def marker_box(self):
        if(self.next_delevery<3):

            if -0.000010217 <= (self.checkpoint.latitude-self.current_location[0]) <= 0.000010217:
                if -0.0000037487 <= (self.checkpoint.longitude-self.current_location[1])<= 0.0000037487:
                    if -0.2 <= (self.checkpoint.altitude-self.current_location[2]) <= 0.2:
                        self.pose_marker_flag = True
                        if(self.pose_mark_cnt==3 and self.pose_marker_flag==True):
                            # print("in the marker box")
                            self.grip_flag.publish('False')
                            self.reset_and_reform()

if __name__ == "__main__":
    planner = PathPlanner()
    rate = rospy.Rate(1/planner.sample_time)
    while not rospy.is_shutdown():
        # if(planner.destination[0]!=0):
        try:
            if(planner.function_switch):
                planner.coordinate_switch()
                planner.obstacle_avoid()
                planner.destination_check()
            else:
                planner.marker_find()
                planner.marker_box()
        except:
            pass
        rate.sleep()