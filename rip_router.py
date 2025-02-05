# -*- coding: utf-8 -*-
import logging
from sim.api import *
from sim.basics import *

'''
在这个文件中创建你的RIP路由器。
'''

# 配置日志记录
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


class RIPRouter(Entity):
    def __init__(self):
        """
        创建一个路由表，使用字典来表示。
        键：路由器的邻居。
        值：一个字典，键为通过该邻居可以到达的路由器，
            值为一个元组（距离，通过哪个端口可以到达该路由器）。
        """
        super(RIPRouter, self).__init__()
        self.routingTable = dict()  # 初始化路由表为空字典
        logging.info("路由器初始化，路由表为空。")

    def handle_rx(self, packet, port):
        """
        通用的分发函数，处理三种类型的数据包：
        DiscoveryPacket, RoutingUpdate, 和 DataPacket。
        """
        logging.debug("在端口 {} 上接收到类型为 {} 的数据包。".format(port, type(packet).__name__))
        if isinstance(packet, DiscoveryPacket):
            self._handleDiscoveryPacket(packet, port)  # 处理发现包
        elif isinstance(packet, RoutingUpdate):
            self._handleRoutingUpdate(packet, port)  # 处理路由更新包
        else:
            self._handleDataPacket(packet, port)  # 处理数据包

    def _handleDiscoveryPacket(self, packet, port):
        """
        处理DiscoveryPacket的函数。
        """
        if packet.is_link_up:
            logging.info("检测到来自 {} 的链路在端口 {} 上上线。".format(packet.src, port))
            self.routingTable[packet.src] = {packet.src: (packet.latency, port)}  # 添加邻居到路由表
            self._announce()  # 通知邻居
        else:
            logging.info("检测到来自 {} 的链路断开。".format(packet.src))
            if packet.src in self.routingTable:
                self.routingTable.pop(packet.src)  # 从路由表中移除邻居
                self._announce()  # 通知邻居

    def _handleRoutingUpdate(self, packet, port):
        """
        处理RoutingUpdate的函数。
        """
        logging.debug("处理来自 {} 的路由更新包，在端口 {} 上。".format(packet.src, port))
        if packet.src not in self.routingTable:
            logging.warning("路由更新来自未知邻居 {}，丢弃。".format(packet.src))
            return

        updated = False
        neighbor_info = self.routingTable[packet.src].copy()
        dests = packet.all_dests()

        for dest in dests:
            new_distance = packet.get_distance(dest) + self.routingTable[packet.src][packet.src][0]
            if dest not in neighbor_info or neighbor_info[dest][0] > new_distance:
                neighbor_info[dest] = (new_distance, port)
                updated = True

        if updated:
            self.routingTable[packet.src] = neighbor_info
            logging.info("路由表已更新，来自 {} 的新路由。".format(packet.src))
            self._announce()  # 通知邻居

    def _handleDataPacket(self, packet, port):
        """
        处理DataPacket的函数。
        """
        logging.debug("处理目的地为 {} 的数据包。".format(packet.dst))
        shortest_path = None

        for neighbor, routes in self.routingTable.items():
            if packet.dst in routes:
                if not shortest_path or routes[packet.dst][0] < shortest_path[0]:
                    shortest_path = routes[packet.dst]

        if shortest_path:
            logging.info("通过端口 {} 转发数据包到 {}。".format(shortest_path[1], packet.dst))
            self.send(packet, shortest_path[1], False)
        else:
            logging.warning("无法转发到目的地 {}，无路由信息。".format(packet.dst))

    def _announce(self):
        """
        每当被调用时，这个announce函数将向邻居宣布当前的路由表。
        """
        logging.info("向邻居宣布路由表。")
        all_shortest_paths = {}

        for routes in self.routingTable.values():
            for dest, (distance, port) in routes.items():
                if dest not in all_shortest_paths or all_shortest_paths[dest][0] > distance:
                    all_shortest_paths[dest] = (distance, port)

        for neighbor, neighbor_routes in self.routingTable.items():
            update_packet = RoutingUpdate()
            neighbor_port = neighbor_routes[neighbor][1]

            for dest, (distance, port) in all_shortest_paths.items():
                if port == neighbor_port:
                    # 避免发送绕回的路径
                    continue
                update_packet.add_destination(dest, distance)

            logging.debug("通过端口 {} 向邻居 {} 发送路由更新包。".format(neighbor_port, neighbor))
            self.send(update_packet, neighbor_port, False)
