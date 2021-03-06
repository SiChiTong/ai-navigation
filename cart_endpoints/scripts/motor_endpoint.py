#!/usr/bin/env python

import serial
import rospy
import bitstruct
from navigation_msgs.msg import VelAngle
from navigation_msgs.msg import EmergencyStop
from std_msgs.msg import Int8, Bool
cart_port = '/dev/ttyUSB9' #hardcoded depending on computer

class MotorEndpoint(object):

    def __init__(self):
        global cart_port
        self.killswitch = False
        self.current_speed = 0.0
        self.goal_speed = 0.0
        self.goal_angle = 0.0
        self.new_vel = True
        self.debug = False
        self.angle_adjust = 0
        self.stop = False
        self.delay_print = 0
        self.brake = int(255)
        self.drove_since_braking = True
        self.cmd_msg = None
        """ Set up the node. """
        rospy.init_node('motor_endpoint')
        rospy.loginfo("Starting motor node!")
        #Connect to arduino for sending speed
        try:
            self.speed_ser = serial.Serial(cart_port, 57600, write_timeout=0)
        except Exception as e:
            print( "Motor_endpoint: " + str(e))
            rospy.logerr("Motor_endpoint: " + str(e))

        rospy.loginfo("Speed serial established")
        """
        Connect to arduino for steering
        """
        self.motion_subscriber = rospy.Subscriber('/nav_cmd', VelAngle, self.motion_callback,
                                                  queue_size=10)
        self.stop_subscriber = rospy.Subscriber('/stop_vehicle', Bool,
                                                      self.stop_callback, queue_size=10)
        self.param_subscriber = rospy.Subscriber('/realtime_a_param_change', Int8, self.param_callback, queue_size=10)
        
        self.debug_subscriber = rospy.Subscriber('/realtime_debug_change', Bool, self.debug_callback, queue_size=10)
        
        rate = rospy.Rate(5)

        while not rospy.is_shutdown():
            if self.cmd_msg is not None:
                self.send_to_motors()
            rate.sleep()

    def motion_callback(self, planned_vel_angle):
        self.cmd_msg = planned_vel_angle  
        self.new_vel = True     

    def param_callback(self, msg):
        self.angle_adjust += (msg.data * 10)

    def stop_callback(self, msg):
        self.stop = msg.data

    def debug_callback(self, msg):
        self.debug = msg.data


    def send_to_motors(self):
        #The first time we get a new target speed and angle we must convert it
        
        if self.new_vel:
            self.new_vel = False
            self.cmd_msg.vel *= 50
            self.cmd_msg.vel_curr *= 50
            if self.cmd_msg.vel > 254:
                self.cmd_msg.vel = 254
            if self.cmd_msg.vel < -254:
                self.cmd_msg.vel = -254
            if self.cmd_msg.vel_curr > 254:
                self.cmd_msg.vel_curr = 254
        target_speed = int(self.cmd_msg.vel) #float64
        current_speed = int(self.cmd_msg.vel_curr) #float64
        #adjust the target_angle range from (-45 <-> 45) to (0 <-> 100)
        # rospy.loginfo("Angle before adjustment: " + str(self.cmd_msg.angle))
        if(self.cmd_msg.angle < -45):
            self.cmd_msg.angle = -45
        if(self.cmd_msg.angle > 45):
            self.cmd_msg.angle = 45
        target_angle = 100 - int(( (self.cmd_msg.angle + 45) / 90 ) * 100)
        # rospy.loginfo("Angle after range adjustment: " + str(target_angle))
        #adjust the target angle additionally using a realtime adjustable testing value
        data = (target_speed,current_speed,target_angle)
        # rospy.loginfo("Before readied data" + str(data))
        data = bytearray(b'\x00' * 5)
            
        #if debug printing is requested print speed and angle info
        if self.debug:
            self.delay_print -= 1
            if self.delay_print <= 0:
                self.delay_print = 5
                rospy.loginfo("Endpoint Angle: " + str(target_angle))
                rospy.loginfo("Endpoint Speed: " + str(target_speed))
            
        # Check for request to stop vehicle
        if self.stop:
            target_speed = (int(-self.brake))
            if(self.drove_since_braking == True):
                self.braking_duration = 3
                self.drove_since_braking = False
            if(self.braking_duration > 0):
                self.brake = 255
                self.braking_duration -= 1
            else:
                self.brake = 0
        else:
            self.drove_since_braking = True
            pass
            #reset the brake force slowly incase a new stop message arises immediatly

        #if the target_speed is negative it actually represents desired braking force
        
        if target_speed < 0:
            bitstruct.pack_into('u8u8u8u8u8', data, 0, 42, 21, 0, abs(target_speed), target_angle)
        else:
            bitstruct.pack_into('u8u8u8u8u8', data, 0, 42, 21, abs(target_speed), 0, target_angle)
        # rospy.loginfo("Readied data: " + str(data) + "\n")
        self.speed_ser.write(data) 

if __name__ == "__main__":
    try:
        MotorEndpoint()
    except rospy.ROSInterruptException:
        pass
