"""
planner.py — A* path planning over the occupancy grid.
Produces a list of waypoint (cell indices) from start to goal.
"""
import heapq
import math
from typing import List, Tuple

from app.slam.mapping import OccupancyGrid


class Planner:
    def __init__(self, grid):
        self.grid = grid

    def astar(self, start, goal):
        rows, cols = self.grid.height, self.grid.width

        def h(a, b):
            return abs(a[0]-b[0]) + abs(a[1]-b[1])

        # Use simple coordinate-based A* without importing internal grid
        sx, sy = start
        gx, gy = goal
        path = []
        visited = set()

        def in_bounds(x, y):
            return 0 <= x < cols and 0 <= y < rows and self.grid._grid[y][x] == FREE

        # Simple rectilinear pathfinding
        def get_neighbors(x, y):
            neighbors = []
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
                nx, ny = x + dx, y + dy
                if in_bounds(nx, ny):
                    neighbors.append((nx, ny))
            return neighbors

        queue = [(h(start, goal), 0, [start])]
        came_from = {}

        while queue:
            _, g, curr_path = heapq.heappop(queue)
            curr_node = curr_path[-1]

            if curr_node == goal:
                return curr_path

            if curr_node in visited:
                continue
            visited.add(curr_node)

            for neighbor in get_neighbors(*curr_node):
                if neighbor not in visited:
                    new_path = curr_path + [neighbor]
                    new_g = g + 1 + (abs(neighbor[0]-start[0]) + abs(neighbor[1]-start[1])) / 10.0
                    heapq.heappush(queue, (new_g + h(neighbor, goal), new_g, new_path))
                    came_from[neighbor] = curr_node

        return []

    def get_grid(self):
        return self.grid._grid.tolist()
