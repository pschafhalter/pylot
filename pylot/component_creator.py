from absl import flags

import pylot.operator_creator

FLAGS = flags.FLAGS


def add_obstacle_detection(center_camera_stream,
                           center_camera_setup=None,
                           pose_stream=None,
                           depth_stream=None,
                           depth_camera_stream=None,
                           segmented_camera_stream=None,
                           ground_obstacles_stream=None,
                           ground_speed_limit_signs_stream=None,
                           ground_stop_signs_stream=None,
                           time_to_decision_stream=None):
    """Adds operators for obstacle detection to the data-flow.

    If the `--perfect_obstacle_detection` flag is set, the method adds a
    perfect detector operator, and returns a stream of perfect obstacles.
    Otherwise, if the `--obstacle_detection` flag is set, the method returns
    a stream of obstacles detected using a trained model.

    Args:
        center_camera_stream (:py:class:`erdos.ReadStream`): Stream on which
            BGR frames are received.
        center_camera_setup
            (:py:class:`~pylot.drivers.sensor_setup.CameraSetup`, optional):
            The setup of the center camera. This setup is used to calculate the
            real-world location of the obstacles.
        pose_stream (:py:class:`erdos.ReadStream`, optional): Stream on
            which pose info is received.
        depth_stream (:py:class:`erdos.ReadStream`, optional): Stream on
            which point cloud or depth frame messages are received.
        depth_camera_stream (:py:class:`erdos.ReadStream`, optional): Stream
            on which depth frames are received.
        segmented_camera__stream (:py:class:`erdos.ReadStream`, optional):
            Stream on which segmented
            :py:class:`~pylot.perception.messages.SegmentedFrameMessage`
            are received.
        ground_obstacles_stream (:py:class:`erdos.ReadStream`, optional):
            Stream on which
            :py:class:`~pylot.perception.messages.ObstaclesMessage` messages
            are received.
        ground_speed_limit_signs_stream
            (:py:class:`erdos.ReadStream`, optional): Stream on which
            :py:class:`~pylot.perception.messages.SpeedSignsMessage`
            messages are received.
        ground_stop_signs_stream (:py:class:`erdos.ReadStream`, optional):
            Stream on which
            :py:class:`~pylot.perception.messages.StopSignsMessage`
            messages are received.

    Returns:
        :py:class:`erdos.ReadStream`: Stream on which
        :py:class:`~pylot.perception.messages.ObstaclesMessage` messages are
        published.
    """
    obstacles_stream = None
    runtime_stream = None
    perfect_obstacles_stream = None
    if FLAGS.obstacle_detection:
        obstacles_stream_wo_depth = None
        if any('efficientdet' in model
               for model in FLAGS.obstacle_detection_model_names):
            obstacles_streams, runtime_streams = pylot.operator_creator.\
                    add_efficientdet_obstacle_detection(
                        center_camera_stream, time_to_decision_stream)
            obstacles_stream_wo_depth = obstacles_streams[0]
            runtime_stream = runtime_streams[0]
        else:
            # TODO: Only returns the first obstacles stream.
            obstacles_streams = pylot.operator_creator.add_obstacle_detection(
                center_camera_stream, time_to_decision_stream)
            obstacles_stream_wo_depth = obstacles_streams[0]
        if FLAGS.planning_type == 'waypoint':
            # Adds an operator that finds the world locations of the obstacles.
            obstacles_stream = pylot.operator_creator.add_obstacle_location_finder(
                obstacles_stream_wo_depth, depth_stream, pose_stream,
                center_camera_setup)
        else:
            obstacles_stream = obstacles_stream_wo_depth

    if FLAGS.perfect_obstacle_detection or FLAGS.evaluate_obstacle_detection:
        assert (pose_stream is not None and depth_camera_stream is not None
                and segmented_camera_stream is not None
                and ground_obstacles_stream is not None
                and ground_speed_limit_signs_stream is not None
                and ground_stop_signs_stream is not None)
        perfect_obstacles_stream = pylot.operator_creator.add_perfect_detector(
            depth_camera_stream, center_camera_stream, segmented_camera_stream,
            pose_stream, ground_obstacles_stream,
            ground_speed_limit_signs_stream, ground_stop_signs_stream)
        if FLAGS.evaluate_obstacle_detection:
            pylot.operator_creator.add_detection_evaluation(
                obstacles_stream_wo_depth, perfect_obstacles_stream)
        if FLAGS.perfect_obstacle_detection:
            obstacles_stream = perfect_obstacles_stream

    if FLAGS.carla_obstacle_detection:
        obstacles_stream = ground_obstacles_stream

    return obstacles_stream, runtime_stream


def add_traffic_light_detection(tl_transform,
                                vehicle_id_stream,
                                release_sensor_stream,
                                pose_stream=None,
                                depth_stream=None,
                                ground_traffic_lights_stream=None):
    """Adds traffic light detection operators.

    The traffic light detectors use a camera with a narrow field of view.

    If the `--perfect_traffic_light_detection` flag is set, the method adds a
    perfect traffic light detector operator, and returns a stream of perfect
    traffic lights. Otherwise, if the `--traffic_light_detection` flag is
    set it returns a stream of traffic lights detected using a trained model.

    Args:
        tl_transform (:py:class:`~pylot.utils.Transform`): Transform of the
             traffic light camera relative to the ego vehicle.
        vehicle_id_stream (:py:class:`erdos.ReadStream`): A stream on which
            the simulator publishes Carla ego-vehicle id.
        pose_stream (:py:class:`erdos.ReadStream`, optional): A stream
            on which pose info is received.
        depth_stream (:py:class:`erdos.ReadStream`, optional): Stream on
            which point cloud messages or depth frames are received.

    Returns:
        :py:class:`erdos.ReadStream`: Stream on which
        :py:class:`~pylot.perception.messages.ObstaclesMessage` traffic light
        messages are published.
    """
    if FLAGS.traffic_light_detection or FLAGS.perfect_traffic_light_detection:
        # Only add the TL camera if traffic light detection is enabled.
        (tl_camera_stream, _,
         tl_camera_setup) = pylot.operator_creator.add_rgb_camera(
             tl_transform, vehicle_id_stream, release_sensor_stream,
             'traffic_light_camera', 45)

    traffic_lights_stream = None
    if FLAGS.traffic_light_detection:
        traffic_lights_stream = \
            pylot.operator_creator.add_traffic_light_detector(
                tl_camera_stream)
        # Adds operator that finds the world locations of the traffic lights.
        traffic_lights_stream = \
            pylot.operator_creator.add_obstacle_location_finder(
                traffic_lights_stream, depth_stream, pose_stream,
                tl_camera_setup)

    if FLAGS.perfect_traffic_light_detection:
        assert (pose_stream is not None
                and ground_traffic_lights_stream is not None)
        # Add segmented and depth cameras with fov 45. These cameras are needed
        # by the perfect traffic light detector.
        (tl_depth_camera_stream, _,
         _) = pylot.operator_creator.add_depth_camera(
             tl_transform, vehicle_id_stream, release_sensor_stream,
             'traffic_light_depth_camera', 45)
        (tl_segmented_camera_stream, _,
         _) = pylot.operator_creator.add_segmented_camera(
             tl_transform, vehicle_id_stream, release_sensor_stream,
             'traffic_light_segmented_camera', 45)

        traffic_lights_stream = \
            pylot.operator_creator.add_perfect_traffic_light_detector(
                ground_traffic_lights_stream, tl_camera_stream,
                tl_depth_camera_stream, tl_segmented_camera_stream,
                pose_stream)

    if FLAGS.carla_traffic_light_detection:
        traffic_lights_stream = ground_traffic_lights_stream

    return traffic_lights_stream


def add_depth(transform, vehicle_id_stream, center_camera_setup,
              depth_camera_stream):
    """Adds operators for depth estimation.

    The operator returns depth frames from CARLA if the
    `--perfect_depth_estimation` flag is set.

    Args:
        transform (:py:class:`~pylot.utils.Transform`): Transform of the
             center camera relative to the ego vehicle.
        vehicle_id_stream (:py:class:`erdos.ReadStream`): A stream on which
            the simulator publishes Carla ego-vehicle id.
        center_camera_setup
            (:py:class:`~pylot.drivers.sensor_setup.CameraSetup`):
            The setup of the center camera.
        depth_camera_stream (:py:class:`erdos.ReadStream`): Stream on which
            depth frames are received.

    Returns:
        :py:class:`erdos.ReadStream`: Stream on which
        :py:class:`~pylot.perception.messages.DepthFrameMessage` messages are
        published.
    """
    depth_stream = None
    if FLAGS.depth_estimation:
        (left_camera_stream,
         right_camera_stream) = pylot.operator_creator.add_left_right_cameras(
             transform, vehicle_id_stream)
        depth_stream = pylot.operator_creator.add_depth_estimation(
            left_camera_stream, right_camera_stream, center_camera_setup)
    if FLAGS.perfect_depth_estimation:
        depth_stream = depth_camera_stream
    return depth_stream


def add_lane_detection(center_camera_stream, pose_stream=None):
    """Adds operators for lane detection.

    If the `--perfect_lane_detection` flag is set, the method adds a perfect
    lane detection operator, and returns a stream of perfect lanes. Otherwise,
    if the `--lane_detection` flag is set the method returns a stream of lanes
    detected using a trained model.

    Args:
        center_camera_stream (:py:class:`erdos.ReadStream`): A stream on which
            camera frames are received.
        pose_stream (:py:class:`erdos.ReadStream`, optional): A stream on
            which pose info is received.

    Returns:
        :py:class:`erdos.ReadStream`: Stream on which
        :py:class:`~pylot.perception.messages.DetectedLaneMessage` are
        published.
    """
    lane_detection_stream = None
    if FLAGS.lane_detection:
        lane_detection_stream = \
            pylot.operator_creator.add_canny_edge_lane_detection(
                center_camera_stream)
    if FLAGS.perfect_lane_detection:
        assert pose_stream is not None
        lane_detection_stream = \
            pylot.operator_creator.add_perfect_lane_detector(pose_stream)
    return lane_detection_stream


def add_obstacle_tracking(center_camera_stream,
                          center_camera_setup,
                          obstacles_stream,
                          depth_stream=None,
                          vehicle_id_stream=None,
                          pose_stream=None,
                          ground_obstacles_stream=None,
                          time_to_decision_stream=None):
    """Adds operators for obstacle tracking.

    If the `--perfect_obstacle_tracking` flag is setup, the method adds an
    operator which uses information from the simulator to perfectly track
    obstacles. Otherwise, if the '--obstacle_tracking' flag is set, the method
    adds operators that use algorithms and trained models to track obstacles.

    Args:
        center_camera_stream (:py:class:`erdos.ReadStream`): Stream on which
            camera frames are received.
        center_camera_setup
            (:py:class:`~pylot.drivers.sensor_setup.CameraSetup`, optional):
            The setup of the center camera. This setup is used to calculate the
            real-world location of the obstacles.
        obstacles_stream (:py:class:`erdos.ReadStream`): Stream on which
            detected obstacles are received.
        depth_stream (:py:class:`erdos.ReadStream`, optional): Stream on
            which point cloud or depth frame messages are received.
        vehicle_id_stream (:py:class:`erdos.ReadStream`, optional): A stream on
             which the simulator publishes Carla ego-vehicle id.
        pose_stream (:py:class:`erdos.ReadStream`, optional): A stream on
            which pose info is received.
        ground_obstacles_stream (:py:class:`erdos.ReadStream`, optional):
            Stream on which
            :py:class:`~pylot.perception.messages.ObstaclesMessage` messages
            are received.

    Returns:
        :py:class:`erdos.ReadStream`: Stream on which
        :py:class:`~pylot.perception.messages.ObstacleTrajectoriesMessage`
        messages are published.
    """
    obstacles_tracking_stream = None
    if FLAGS.obstacle_tracking:
        obstacles_wo_history_tracking_stream = \
            pylot.operator_creator.add_obstacle_tracking(
                obstacles_stream,
                center_camera_stream,
                time_to_decision_stream)
        obstacles_tracking_stream = \
            pylot.operator_creator.add_obstacle_location_history(
                obstacles_wo_history_tracking_stream, depth_stream,
                pose_stream, ground_obstacles_stream, vehicle_id_stream
                center_camera_setup)
    if FLAGS.perfect_obstacle_tracking:
        assert (pose_stream is not None
                and ground_obstacles_stream is not None)
        obstacles_tracking_stream = \
            pylot.operator_creator.add_perfect_tracking(
                vehicle_id_stream, ground_obstacles_stream, pose_stream)

    if FLAGS.evaluate_obstacle_tracking:
        pylot.operator_creator.add_tracking_evaluation(
            obstacles_wo_history_tracking_stream, obstacles_stream)

    return obstacles_tracking_stream


def add_segmentation(center_camera_stream, ground_segmented_stream=None):
    """Adds operators for pixel semantic segmentation.

    If the `--perfect_segmentation` flag is set, the method returns a stream
    of perfectly frames. Otherwise, if the `--segmentation` flag is set, the
    method adds operators that use trained models.

    Args:
        center_camera_stream (:py:class:`erdos.ReadStream`): Stream on which
            camera frames are received.
        ground_segmented_stream (:py:class:`erdos.ReadStream`, optional):
            Stream on which perfectly segmented
            :py:class:`~pylot.perception.messages.SegmentedFrameMessage` are
            received.

    Returns:
        :py:class:`erdos.ReadStream`: Stream on which semantically segmented
        frames are published.
    """
    segmented_stream = None
    if FLAGS.segmentation:
        segmented_stream = pylot.operator_creator.add_segmentation(
            center_camera_stream)
        if FLAGS.evaluate_segmentation:
            assert ground_segmented_stream is not None
            pylot.operator_creator.add_segmentation_evaluation(
                ground_segmented_stream, segmented_stream)
    elif FLAGS.perfect_segmentation:
        assert ground_segmented_stream is not None
        return ground_segmented_stream
    return segmented_stream


def add_prediction(obstacles_tracking_stream,
                   vehicle_id_stream,
                   camera_transform,
                   release_sensor_stream,
                   pose_stream=None,
                   point_cloud_stream=None,
                   lidar_setup=None):
    """Adds prediction operators.

    Args:
        obstacles_tracking_stream (:py:class:`erdos.ReadStream`):
            Stream on which
            :py:class:`~pylot.perception.messages.ObstacleTrajectoriesMessage`
            are received.
        vehicle_id_stream (:py:class:`erdos.ReadStream`): A stream on
             which the simulator publishes Carla ego-vehicle id.
        camera_transform (:py:class:`~pylot.utils.Transform`): Transform of the
             center camera relative to the ego vehicle.
        pose_stream (:py:class:`erdos.ReadStream`, optional): Stream on
             which pose info is received.
        point_cloud_stream (:py:class:`erdos.ReadStream`, optional): Stream on
            which point cloud messages are received.

    Returns:
        :py:class:`erdos.ReadStream`: Stream on which
        :py:class:`~pylot.prediction.messages.PredictionMessage` messages are
        published.
    """

    prediction_stream = None
    if FLAGS.prediction:
        if FLAGS.prediction_type == 'linear':
            prediction_stream = pylot.operator_creator.add_linear_prediction(
                obstacles_tracking_stream)
        elif FLAGS.prediction_type == 'r2p2':
            assert pose_stream is not None
            assert point_cloud_stream is not None
            assert lidar_setup is not None
            prediction_stream = pylot.operator_creator.add_r2p2_prediction(
                pose_stream, point_cloud_stream, obstacles_tracking_stream,
                vehicle_id_stream, lidar_setup)
        else:
            raise ValueError('Unexpected prediction_type {}'.format(
                FLAGS.prediction_type))
        if FLAGS.evaluate_prediction:
            assert pose_stream is not None
            pylot.operator_creator.add_prediction_evaluation(
                pose_stream, obstacles_tracking_stream, prediction_stream)
        if FLAGS.visualize_prediction:
            pylot.operator_creator.add_prediction_visualizer(
                obstacles_tracking_stream, prediction_stream,
                vehicle_id_stream, camera_transform, release_sensor_stream)
    return prediction_stream


def add_planning(goal_location, pose_stream, prediction_stream, camera_stream,
                 obstacles_stream, traffic_lights_stream, open_drive_stream,
                 global_trajectory_stream, time_to_decision_stream):
    """Adds planning operators.

    Args:
        goal_location (:py:class:`~pylot.utils.Location`): The destination.
        pose_stream (:py:class:`erdos.ReadStream`): Stream on which
            pose info is received.
        prediction_stream (:py:class:`erdos.ReadStream`): Stream of
            :py:class:`~pylot.prediction.messages.PredictionMessage` messages
            for predicted obstacles.
        camera_stream (:py:class:`erdos.ReadStream`): Stream of
            :py:class:`~pylot.perception.messages.FrameMessage` messages
            for camera frames.
        obstacles_stream (:py:class:`erdos.ReadStream`): Stream of
            :py:class:`~pylot.perception.messages.ObstaclesMessage` messages
            for obstacles.
        traffic_lights_stream (:py:class:`erdos.ReadStream`): Stream of
            :py:class:`~pylot.perception.messages.TrafficLightsMessage`
            messages for traffic lights.
        open_drive_stream (:py:class:`erdos.ReadStream`, optional):
            Stream on which open drive string representations are received.
            Operators can construct HDMaps out of the open drive strings.
        global_trajectory_stream (:py:class:`erdos.ReadStream`, optional):
            Stream on which global trajectory is received.

    Returns:
        :py:class:`erdos.ReadStream`: Stream on which the waypoints are
        published.
    """
    if FLAGS.planning_type == 'waypoint':
        waypoints_stream = pylot.operator_creator.add_waypoint_planning(
            pose_stream, open_drive_stream, global_trajectory_stream,
            obstacles_stream, traffic_lights_stream, goal_location)
    elif FLAGS.planning_type == 'rrt_star':
        waypoints_stream = pylot.operator_creator.add_rrt_star_planning(
            pose_stream, prediction_stream, global_trajectory_stream,
            open_drive_stream, time_to_decision_stream, goal_location)
    elif FLAGS.planning_type == 'frenet_optimal_trajectory':
        waypoints_stream = pylot.operator_creator.add_fot_planning(
            pose_stream, prediction_stream, global_trajectory_stream,
            open_drive_stream, time_to_decision_stream, goal_location)
    elif FLAGS.planning_type == 'hybrid_astar':
        waypoints_stream = pylot.operator_creator.add_hybrid_astar_planning(
            pose_stream, prediction_stream, global_trajectory_stream,
            open_drive_stream, time_to_decision_stream, goal_location)
    else:
        raise ValueError('Unexpected planning_type {}'.format(
            FLAGS.planning_type))
    if FLAGS.visualize_waypoints:
        pylot.operator_creator.add_waypoint_visualizer(waypoints_stream,
                                                       camera_stream,
                                                       pose_stream)
    return waypoints_stream


def add_control(pose_stream, waypoints_stream):
    """Adds ego-vehicle control operators.

    Args:
        pose_stream (:py:class:`erdos.ReadStream`, optional): Stream on
            which pose info is received.
        waypoints_stream (:py:class:`erdos.ReadStream`): Stream on which
            waypoints are received.

    Returns:
        :py:class:`erdos.ReadStream`: Stream on which
        :py:class:`~pylot.control.messages.ControlMessage` messages are
        published.
    """
    if FLAGS.control_agent == 'pid':
        control_stream = pylot.operator_creator.add_pid_agent(
            pose_stream, waypoints_stream)
    elif FLAGS.control_agent == 'mpc':
        control_stream = pylot.operator_creator.add_mpc_agent(
            pose_stream, waypoints_stream)
    elif FLAGS.control_agent in ['carla_auto_pilot', 'manual']:
        # TODO: Hack! We synchronize on a single stream, based on a
        # guesestimate of which stream is slowest.
        control_stream = pylot.operator_creator.add_synchronizer(
            waypoints_stream)
    else:
        raise ValueError('Unexpected control_agent {}'.format(
            FLAGS.control_agent))

    if FLAGS.evaluate_control:
        pylot.operator_creator.add_control_evaluation(pose_stream,
                                                      waypoints_stream)
    return control_stream
