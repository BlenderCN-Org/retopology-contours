'''
Copyright (C) 2013 CG Cookie
http://cgcookie.com
hello@cgcookie.com

Created by Patrick Moore

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

####class definitions####

import bpy
import math
import time
import copy
from mathutils import Vector, Quaternion
from mathutils.geometry import intersect_point_line, intersect_line_plane
import contour_utilities
from bpy_extras.view3d_utils import location_3d_to_region_2d
from bpy_extras.view3d_utils import region_2d_to_vector_3d
from bpy_extras.view3d_utils import region_2d_to_location_3d
import blf
#from development.cgc-retopology import contour_utilities


class SketchEndPoint(object):
    def __init__(self,context, parent, end, color = (.1,.2,.8,1), size = 4, mouse_radius = 10):
        '''
        end = enum in 'HEAD' or 'TAIL'
        '''
        settings = context.user_preferences.addons['cgc-retopology'].preferences
        
        if len(parent.raw_world) < 3:
            return None
        
        self.desc = 'SKETCH_END'
        self.color = color
        
        if end == 'HEAD':
            self.world_position = parent.raw_world[0].copy()
            self.dir = self.world_position - parent.raw_world[1]
            self.color = (settings.sketch_color3[0], settings.sketch_color3[1],settings.sketch_color3[2],1)
            
        if end == 'TAIL':
            self.world_position = parent.raw_world[-1].copy()
            self.dir = self.world_position
            self.color = (settings.sketch_color4[0], settings.sketch_color4[1],settings.sketch_color4[2],1)
            
        self.screen = location_3d_to_region_2d(context.region, context.space_data.region_3d,self.world_position)
        
        self.parent = parent
        
        self.size = size
        self.mouse_rad = mouse_radius
        
    def draw(self,context):
        contour_utilities.draw_3d_points(context, [self.world_position], self.color, self.size)
        
class ContourControlPoint(object):
    
    def __init__(self, parent, x, y, color = (1,0,0,1), size = 2, mouse_radius=10):
        self.desc = 'CONTROL_POINT'
        self.x = x
        self.y = y
        self.world_position = None #to be updated later
        self.color = color
        self.size = size
        self.mouse_rad = mouse_radius
        self.parent = parent
        
    def mouse_over(self,x,y):
        dist = (self.x -x)**2 + (self.y - y)**2
        #print(dist < 100)
        if dist < 100:
            return True
        else:
            return False
        
    def screen_from_world(self,context):
        point = location_3d_to_region_2d(context.region, context.space_data.region_3d,self.world_position)
        self.x = point[0]
        self.y = point[1]
        
    def screen_to_world(self,context):
        region = context.region  
        rv3d = context.space_data.region_3d
        if self.world_position:
            self.world_position = region_2d_to_location_3d(region, rv3d, (self.x, self.y),self.world_position)

class ExistingVertList(object):
    def __init__(self, verts, edges, mx):
        self.desc = 'EXISTING_VERT_LIST'
        
        edge_keys = [[ed.verts[0].index, ed.verts[1].index] for ed in edges]
        remaining_keys = [i for i in range(1,len(edge_keys))]
        
        vert_inds_unsorted = [vert.index for vert in verts]
        vert_inds_sorted = [edge_keys[0][0], edge_keys[0][1]]
        
        iterations = 0
        max_iters = math.factorial(len(remaining_keys))
        while len(remaining_keys) > 0 and iterations < max_iters:
            print(remaining_keys)
            iterations += 1
            for key_index in remaining_keys:
                l = len(vert_inds_sorted) -1
                key_set = set(edge_keys[key_index])
                last_v = {vert_inds_sorted[l]}
                if  key_set & last_v:
                    vert_inds_sorted.append(int(list(key_set - last_v)[0]))
                    remaining_keys.remove(key_index)
                    break
        
        if vert_inds_sorted[0] == vert_inds_sorted[-1]:
            cyclic = True
            vert_inds_sorted.pop()
        else:
            cyclic = False
            
        self.eds_simple = [[i,i+1] for i in range(0,len(vert_inds_sorted)-1)]
        if cyclic:
            self.eds_simple.append([len(vert_inds_sorted)-1,0])
            
        self.verts_simple = []
        for i in vert_inds_sorted:
            v = verts[vert_inds_unsorted.index(i)]
            self.verts_simple.append(mx * v.co)
            
        
    def connectivity_analysis(self,other):
        
        
        COM_self = contour_utilities.get_com(self.verts_simple)
        COM_other = contour_utilities.get_com(other.verts_simple)
        delta_com_vect = COM_self - COM_other  #final - initial :: self - other
        delta_com_vect.normalize()
        

        
        ideal_to_com = 0
        for i, v in enumerate(self.verts_simple):
            connector = v - other.verts_simple[i]  #continue convention of final - initial :: self - other
            connector.normalize()
            align = connector.dot(delta_com_vect)
            #this shouldnt happen but it appears to be...shrug
            if align < 0:
                align *= -1    
            ideal_to_com += align
        
        ideal_to_com = 1/len(self.verts_simple) * ideal_to_com
        
        return ideal_to_com
        
        
    def align_to_other(self,other, auto_align = True):
        
        '''
        Modifies vert order of self to  provide best
        bridge between self verts and other loop
        '''
        verts_1 = other.verts_simple
        
        eds_1 = other.eds_simple
        
        print('testing alignment')
        if 0 in eds_1[-1]:
            cyclic = True
            print('cyclic vert chain')
        else:
            cyclic = False
        
        if len(verts_1) != len(self.verts_simple):
            #print(len(verts_1))
            #print(len(self.verts_simple))
            print('non uniform loops, stopping until your developer gets smarter')
            return
            
        if cyclic:

            V1_0 = verts_1[1] - verts_1[0]
            V1_1 = verts_1[2] - verts_1[1]
            
            V2_0 = self.verts_simple[1] - self.verts_simple[0]
            V2_1 = self.verts_simple[2] - self.verts_simple[1]
            
            no_1 = V1_0.cross(V1_1)
            no_1.normalize()
            no_2 = V2_0.cross(V2_1)
            no_2.normalize()
            
            if no_1.dot(no_2) < 0:
                no_2 = -1 * no_2
            
            #average the two directions    
            ideal_direction = no_1.lerp(no_1,.5)
        
            curl_1 = contour_utilities.discrete_curl(verts_1, ideal_direction)
            curl_2 = contour_utilities.discrete_curl(self.verts_simple, ideal_direction)
            
            if curl_1 * curl_2 < 0:
                self.verts_simple.reverse()
                

            edge_len_dict = {}
            for i in range(0,len(verts_1)):
                for n in range(0,len(self.verts_simple)):
                    edge = (i,n)
                    vect = self.verts_simple[n] - verts_1[i]
                    edge_len_dict[edge] = vect.length
            
            shift_lengths = []
            #shift_cross = []
            for shift in range(0,len(self.verts_simple)):
                tmp_len = 0
                #tmp_cross = 0
                for i in range(0, len(self.verts_simple)):
                    shift_mod = int(math.fmod(i+shift, len(self.verts_simple)))
                    tmp_len += edge_len_dict[(i,shift_mod)]
                shift_lengths.append(tmp_len)
                   
            final_shift = shift_lengths.index(min(shift_lengths))
            if final_shift != 0:
                print('pre rough shift alignment % f' % self.connectivity_analysis(other))
                print("rough shifting verts by %i segments" % final_shift)
                self.int_shift = final_shift
                self.verts_simple = contour_utilities.list_shift(self.verts_simple, final_shift)
                print('post rough shift alignment % f' % self.connectivity_analysis(other))    
                
        
        else:
            #if the segement is not cyclic
            #all we have to do is compare the endpoints
            Vtotal_1 = verts_1[-1] - verts_1[0]
            Vtotal_2 = self.verts_simple[-1] - self.verts_simple[0]
    
            if Vtotal_1.dot(Vtotal_2) < 0:
                print('reversing path 2')
                self.verts_simple.reverse()
                      

class PolySkecthLine(object):
    
    def __init__(self, context, raw_points,
                 cull_factor = 3,
                 smooth_factor = 5,
                 feature_factor = 5):
        
        settings = context.user_preferences.addons['cgc-retopology'].preferences
        ####IDENTIFIER###
        self.desc = 'SKETCH_LINE'
        self.select = True
        ####DATA####
        if len(raw_points):
            self.raw_screen = [raw_points[0]]
        else:
            self.raw_screen = []
        
        #toss a bunch of data
        for i, v in enumerate(raw_points):
            if not math.fmod(i, cull_factor):
                self.raw_screen.append(v)
        
        #culled raw_screen
        #raycast onto object
        self.raw_world = []
        
        #atenuated and smoothed
        self.world_path = []
        
        #a collection of verts to draw for testing
        self.test_verts = []
        
        
        #this is free data from raycast
        #and from ob.closest_point
        self.path_seeds = []
        self.path_normals = []
        
        self.poly_seeds = []
        self.poly_normals = []
        
        
        #region 2d version of world path
        self.screen_path = []
        
        #detected features of screen path
        self.knots = []
        
        #locations of perpendicular
        #poly edges
        self.poly_nodes = []
        self.extrudes_u = []
        self.extrudes_d = []
        
        
        
        ####WIDGETY THINGS####
        self.head = None
        self.tail = None
        
        ####PROCESSIG CONSTANTS###
        self.cull_factor = cull_factor
        self.smooth_factor = smooth_factor
        self.feature_factor = feature_factor
        
        self.poly_loc = 'CENTERED' #ABOVE, #BELOW
        
        #this is an interesting connundrum
        #do we aim for n segmetns or a density/quad size
        self.segments = 10
        self.quad_width = 1
        self.quad_length = 1
        
        ####VISULAIZTION STUFF####
        self.color1 = (settings.sketch_color1[0], settings.sketch_color1[1],settings.sketch_color1[2],1)
        self.color2 = (settings.sketch_color2[0], settings.sketch_color2[1],settings.sketch_color2[2],1)
        self.color3 = (settings.sketch_color3[0], settings.sketch_color3[1],settings.sketch_color3[2],1)
        self.color4 = (settings.sketch_color4[0], settings.sketch_color4[1],settings.sketch_color4[2],1)
        self.color5 = (settings.sketch_color5[0], settings.sketch_color5[1],settings.sketch_color5[2],1)
        

    def active_element(self,context,x,y):
        settings = context.user_preferences.addons['cgc-retopology'].preferences
        mouse_loc = Vector((x,y))
        
        if self.head:
            a = self.head.screen
            v = a - mouse_loc
            if v.length < self.head.mouse_rad:
                return self.head
            
        if self.tail:
            a = self.tail.screen
            v = a - mouse_loc
            if v.length < self.tail.mouse_rad:
                return self.tail
            
        
        if len(self.knots):
            for i in self.knots:
                a = location_3d_to_region_2d(context.region, context.space_data.region_3d, self.knots[i])
                v = a - mouse_loc
                if v.length < 10:
                    return self.self.knots[i]
            
        if len(self.world_path):
            
            #Check by testing distance to all edges
            active_self = False
            
            for i in range(0,len(self.world_path) -1):
                
                a = location_3d_to_region_2d(context.region, context.space_data.region_3d, self.world_path[i])
                b = location_3d_to_region_2d(context.region, context.space_data.region_3d, self.world_path[i+1])
                intersect = intersect_point_line(mouse_loc, a, b)
        
                dist = (intersect[0] - mouse_loc).length_squared
                bound = intersect[1]
                if (dist < 100) and (bound < 1) and (bound > 0):
                    active_self = True
                    
                    break
            
            if active_self:    
                return self
            else:
                return None
        
    def ray_cast_path(self,context, ob):
        
        settings = context.user_preferences.addons['cgc-retopology'].preferences
        self.quad_length = ob.dimensions.length * 1/settings.density_factor
        self.quad_width = self.quad_length
        
        region = context.region  
        rv3d = context.space_data.region_3d
        self.raw_world = []
        for v in self.raw_screen:
            vec = region_2d_to_vector_3d(region, rv3d, v)
            loc = region_2d_to_location_3d(region, rv3d, v, vec)

            a = loc + 3000*vec
            b = loc - 3000*vec

            mx = ob.matrix_world
            imx = mx.inverted()
            hit = ob.ray_cast(imx*a, imx*b)
            
            if hit[2] != -1:
                self.raw_world.append(mx * hit[0])
                
        self.head = SketchEndPoint(context, self, 'HEAD')
        self.tail = SketchEndPoint(context, self, 'TAIL')
        
        
    def find_knots(self):
        print('find those knots')
        box_diag = contour_utilities.diagonal_verts(self.raw_world)
        error = 1/self.feature_factor * box_diag
        
        self.knots = contour_utilities.simplify_RDP(self.raw_world, error)
        
        
    def smooth_path(self,context, ob = None):
        print('              ')

        start_time = time.time()
        print(self.raw_world[1])
        #clear the world path if need be
        self.world_path = []
        
        if ob:
            mx = ob.matrix_world
            imx = mx.inverted()
            
        if len(self.knots) > 2:
            
            #split the raw
            segments = []
            for i in range(0,len(self.knots) - 1):
                segments.append([self.raw_world[m] for m in range(self.knots[i],self.knots[i+1])])
                
        else:
            segments = [[v.copy() for v in self.raw_world]]
        
        for segment in segments:
            for n in range(self.smooth_factor - 1):
                contour_utilities.relax(segment)
                
                #resnap so we don't loose the surface
                if ob:
                    for i, vert in enumerate(segment):
                        snap = ob.closest_point_on_mesh(imx * vert)
                        segment[i] = mx * snap[0]
            
            self.world_path.extend(segment)
        
        
        end_time = time.time()
        print('smoothed and snapped %r in %f seconds' % (ob != None, end_time - start_time)) 
        
        #resnap everthing we can to get normals an stuff
        #TODO do this the last time on the smooth factor duh
        self.snap_to_object(ob)
        
        self.head = SketchEndPoint(context, self, 'HEAD')
        self.tail = SketchEndPoint(context, self, 'TAIL')
    
    def snap_to_object(self,ob, raw = True, world = True, polys = True):
        
        mx = ob.matrix_world
        imx = mx.inverted()
        
        print('made to snap...is this the problem or the solution?')
        if raw and len(self.raw_world):
            for i, vert in enumerate(self.raw_world):
                snap = ob.closest_point_on_mesh(imx * vert)
                self.raw_world[i] = mx * snap[0]
                
                
        if world and len(self.world_path):
            self.path_normals = []
            self.path_seeds = []
            for i, vert in enumerate(self.world_path):
                snap = ob.closest_point_on_mesh(imx * vert)
                self.world_path[i] = mx * snap[0]
                self.path_normals.append(mx.to_3x3() * snap[1])
                self.path_seeds.append(snap[2])
                
        if polys and len(self.poly_nodes):
            self.poly_normals = []
            self.poly_seeds = []
            for i, vert in enumerate(self.poly_nodes):
                snap = ob.closest_point_on_mesh(imx * vert)
                self.poly_nodes[i] = mx * snap[0]
                self.poly_normals.append(mx.to_3x3() * snap[1])
                self.poly_seeds.append(snap[2])
                
            
    def intersect_other_paths(self,context, other_paths, separate_other = False):
        '''
        '''
        
        new_sketches = [] 
        #no guarantees we will find intersections in order
        intersection_points = {}  #dictionary keeping the index of the first vert in edge intersected mapped to the intersection
        intersection_inds = []  #the indices of verts (and the i + 1 edge)
        for line in other_paths:
            #test tip and tails:
            tip_tip = self.head.world_position - line.head.world_position
            tip_tail = self.head.world_position - line.tail.world_position
            tail_tip = self.tail.world_position - line.head.world_position
            tail_tail = self.tail.world_position - line.tail.world_position
            #print('tips and tails')
            #print('lengths tiptip: %f, \n tip_tail: %f, \n tail_tip: %f, \n tail_tail: %f' % (tip_tip.length, tip_tail.length, tail_tail.length, tail_tip.length))
                    
            new_intersects, inds_1, inds_2 = contour_utilities.intersect_paths(self.world_path, line.world_path, cyclic1 = False, cyclic2 = False, threshold = .1)
            
            print('   ')
            print('raw new intersection indices and verts')
            print(inds_1)
            print(new_intersects)
            print('   ')
            
            #easier to just remove the tip and tail intersections
            #TODO make sure thresholds are correlated here
            if tip_tip.length < .1 or tip_tail.length < .1:
                print('tip intersection')
                new_intersects.pop(0)
            if tail_tip.length < .1 or tail_tail.length < .1:
                print('tail intersection')
                new_intersects.pop()
                
        
            if new_intersects != []:
                intersection_inds.extend(inds_1)
                for i, index in enumerate(inds_1):
                    intersection_points[index] = new_intersects[i]
                    
                    #scary code within code reference :-/
                    if separate_other:
                        print('             ')
                        print('going to split the other one hopefully in a logical place!')
                        fragments = line.intersect_other_paths(context,[self],separate_other = False)
                        if fragments != []:
                            line.create_vert_nodes()
                            new_sketches.extend(fragments)
           
        if intersection_inds != []:
            #split up the segments
            print('intersections were found')
            n = len(self.raw_world) - 1
            
            verts = self.world_path.copy()

            
            intersection_inds.sort()

            if n not in intersection_inds:
                intersection_inds.append(n+1)
            #the first edge may have been intersected
            #meaning the first ver will be there already
            if 0 not in intersection_inds:
                intersection_inds.insert(0,0)
            
            segments = []
            short_segments = []
            print('the world path is %i long' % len(self.world_path))
            print('these are the intersection indices')
            print(intersection_inds)
            for i in range(0,len(intersection_inds) - 1):
                
                start_index = intersection_inds[i]
                end_index = intersection_inds[i+1]
                print('start index: %i stop_index: %i' % (start_index, end_index))
                
                #can't wrap my head around why this needs to happen
                #I think we are getting some bad references where things
                #are pointing ot old copies  #major bug at the moment
            
                seg = verts[start_index:end_index]
                
                if i >= 1:
                    #replace the start vert with the intersection vert
                    if start_index in intersection_points:
                        seg.insert(0,intersection_points[start_index])
                    
                if end_index < n:
                    #tag the next intersection point on the end
                    seg.append(intersection_points[end_index])
                
                
                if len(seg) < 3:
                    print('interpolating tip or tail because it has %i verts' % len(seg))
                    new_seg = contour_utilities.space_evenly_on_path(seg, [[0,1],[1,2]], 4, 0)[0]
                    short_segments.append(new_seg)
                
                else:
                    segments.append(seg)
                    
                if segments == []:
                    segments = short_segments
            
            if segments != []:
                self.world_path = segments[0]
                self.raw_world = segments[0]
                self.head = SketchEndPoint(context, self, 'HEAD')
                self.tail = SketchEndPoint(context, self, 'TAIL')
            
            if len(segments) > 1:
                print('split line into %i segments' % len(segments))
                for i in range(1,len(segments)):
                    #powerful copy module....then replace the world part
                    sketch = copy.deepcopy(self)
                    sketch.raw_world = segments[i]
                    sketch.world_path = segments[i]
                    sketch.head = SketchEndPoint(context, sketch, 'HEAD')
                    sketch.tail = SketchEndPoint(context, sketch, 'TAIL')
                    new_sketches.append(sketch)
                
                    
        return new_sketches
            
    
    def cut_by_path(self):
        '''
        deep cut using contour tool to cut between each
        path vertex.  Most strict, slowest, and most sensitive
        to error.  However,  it will give best results on deep
        crevices.
        '''
        
        print('not implemented')
        
        
            
    def cut_by_endpoints(self,ob, bme):
        '''
        good for straigh cuts in 1 of 3 dimensions
        so as long as your path is a straight line from
        end to end, this is the best method.
        '''
        
        if len(self.path_seeds) < 3:
            print('no path seed points, perhaps this stroke is bad?')
            print('forcing resnap of all paths now.  Try to cut again.')
            self.snap_to_object(ob)
            return
        mx = ob.matrix_world
        
        #TODO  Check for a world path
        pt1 = self.world_path[0]
        pt2 = self.world_path[-1]
        
        
        seed1 = self.path_seeds[0]
        seed2 = self.path_seeds[-1]
        
        #normals parallel to the plane
        B1 = self.path_normals[0]
        B2 = self.path_normals[-1]
        
        B_avg = B1.lerp(B2,.5)
        T = pt2 - pt1
        
        B_avg.normalize()
        T.normalize()
        
        no = B_avg.cross(T)
        
        new_verts = contour_utilities.cross_section_2_seeds(bme, mx, pt1, no, pt1, seed1, pt2, seed2, max_tests = 1000)
        
        if len(new_verts) > 0:
            self.test_verts = [mx * v for v in new_verts]
        
        
        
        
            
    def create_vert_nodes(self,context, mode = 'QUAD_SIZE'):
        '''
        mode enum in 'N_SEGMENTS','QUAD_SIZE'
        '''
        self.poly_nodes = []
        curve_len = contour_utilities.get_path_length(self.world_path)
        
        if mode == 'QUAD_SIZE':
            self.segments = round(curve_len/self.quad_length)
        
        elif mode == 'SEGMENTS' and self.segments > 0:
            self.quad_length = curve_len/self.segments
            
            
        if self.segments <= 1:
            print('not worth it')
            return
        
        
        desired_density = 1/self.quad_length 
        
         
        if len(self.knots) > 2:
            segments = []
            for i in range(0,len(self.knots) - 1):
                segments.append(self.world_path[self.knots[i]:self.knots[i+1]+1])
                  
        else:
            segments = [self.world_path]
            
        
        for i, segment in enumerate(segments):
            segment_length = contour_utilities.get_path_length(segment)
            n_segments = round(segment_length * desired_density)
            vs = contour_utilities.space_evenly_on_path(segment, [[0,1],[1,2]], n_segments, 0, debug = False)[0]
            if i > 0:
                self.poly_nodes.extend(vs[1:len(vs)])
            else:
                self.poly_nodes.extend(vs[:len(vs)])
        
        self.head = SketchEndPoint(context, self, 'HEAD')
        self.tail = SketchEndPoint(context, self, 'TAIL')
            
    def generate_quads(self,ob,width):
        mx = ob.matrix_world
        imx = mx.inverted()
        
        self.extrudes_u = []
        self.extrudes_d = []
        
        #not necessary?  #already happened?
        #definitely not necesary if we cut the object
        self.snap_to_object(ob, raw = False, world = False, polys = True)
            
            
        for i, v in enumerate(self.poly_nodes):
            if i == 0:
                v = self.poly_nodes[i+1] - self.poly_nodes[i]
            
            elif i == len(self.poly_nodes) - 1:
                v = self.poly_nodes[i] - self.poly_nodes[i-1]
                
            else:
                v1 = self.poly_nodes[i] - self.poly_nodes[i-1]
                v2 = self.poly_nodes[i+1] - self.poly_nodes[i]
                v = v1.lerp(v2, .5)
                
            ext = self.poly_normals[i].cross(v)
            ext.normalize()
            
            self.extrudes_u.append(self.poly_nodes[i] + .5 * width * ext)
            self.extrudes_d.append(self.poly_nodes[i] - .5 * width * ext)    
            
            
        print('make the quads')
        
        
        
    def draw(self,context):
        
        #if len(self.raw_world) > 2:
            #contour_utilities.draw_polyline_from_3dpoints(context, self.raw_world, self.color1, 1, 'GL_LINES')
        
        if len(self.test_verts) > 0:
            contour_utilities.draw_3d_points(context, self.test_verts, self.color5, 3)
            
        #draw the smothed path
        if len(self.world_path) > 1 and len(self.poly_nodes) < 2:
            contour_utilities.draw_polyline_from_3dpoints(context, self.world_path, self.color2, 1, 'GL_LINE_STIPPLE')
            contour_utilities.draw_3d_points(context, self.world_path, self.color1, 3)
        #draw the knots
        if len(self.knots) > 2:
            points = [self.raw_world[i] for i in self.knots]
            contour_utilities.draw_3d_points(context, points, self.color3, 5)
            
        #draw the knots
        if len(self.poly_nodes) > 2 and len(self.extrudes_u) == 0:
            contour_utilities.draw_3d_points(context, self.poly_nodes, self.color1, 3)
            contour_utilities.draw_polyline_from_3dpoints(context, self.poly_nodes, self.color2, 1, 'GL_LINE_STIPPLE')
        
        if len(self.extrudes_u) > 2:
            contour_utilities.draw_3d_points(context, self.extrudes_u, self.color4, 2)
            contour_utilities.draw_3d_points(context, self.extrudes_d, self.color4, 2)
            contour_utilities.draw_polyline_from_3dpoints(context, self.extrudes_u, (0,1,0,1), 1, 'GL_LINE_STIPPLE')
            contour_utilities.draw_polyline_from_3dpoints(context, self.extrudes_d, (0,1,0,1), 1, 'GL_LINE_STIPPLE')
            
            for i, v in enumerate(self.extrudes_u):
                contour_utilities.draw_polyline_from_3dpoints(context, [self.extrudes_u[i],self.extrudes_d[i]], (0,1,0,1), 1, 'GL_LINE_STIPPLE')
            
        if self.head:
            self.head.draw(context)
        if self.tail:
            self.tail.draw(context)
            
class ContourCutLine(object): 
    
    def __init__(self, x, y, line_width = 3,
                 stroke_color = (0,0,1,1), 
                 handle_color = (1,0,0,1),
                 geom_color = (0,1,0,1),
                 vert_color = (0,.2,1,1)):
        
        self.desc = "CUT_LINE"
        self.select = True
        self.head = ContourControlPoint(self,x,y, color = handle_color)
        self.tail = ContourControlPoint(self,x,y, color = handle_color)
        #self.plane_tan = ContourControlPoint(self,x,y, color = (.8,.8,.8,1))
        #self.view_dir = view_dir
        self.target = None
 
        self.updated = False
        self.plane_pt = None  #this will be a point on an object surface...calced after ray_casting
        self.plane_com = None  #this will be a point in the object interior, calced after cutting a contour
        self.plane_no = None
        
        #these points will define two orthogonal vectors
        #which lie tangent to the plane...which we can use
        #to draw a little widget on the COM
        self.plane_x = None
        self.plane_y = None
        self.plane_z = None
        
        self.vec_x = None
        self.vec_y = None
        #self.vec_z is the plane normal
        
        self.seed_face_index = None
        
        #high res coss section
        #@ resolution of original mesh
        self.verts = []
        self.verts_screen = []
        self.edges = []
        #low res derived contour
        self.verts_simple = []
        self.eds_simple = []
        
        #screen cache for fast selection
        self.verts_simple_screen = []
        
        #variable used to shift loop beginning on high res loop
        self.shift = 0
        self.int_shift = 0
        
        #visual stuff
        self.line_width = line_width
        self.stroke_color = stroke_color
        self.geom_color = geom_color
        self.vert_color = vert_color
        
    def update_screen_coords(self,context):
        self.verts_screen = [location_3d_to_region_2d(context.region, context.space_data.region_3d, loc) for loc in self.verts]
        self.verts_simple_screen = [location_3d_to_region_2d(context.region, context.space_data.region_3d, loc) for loc in self.verts_simple]
        
          
    def draw(self,context, settings, three_dimensional = True, interacting = False):
        '''
        setings are the addon preferences for contour tools
        '''
        
        debug = settings.debug
        #settings = context.user_preferences.addons['cgc-retopology'].preferences
        
        #this should be moved to only happen if the view changes :-/  I'ts only
        #a few hundred calcs even with a lot of lines. Waste not want not.
        if self.head and self.head.world_position:
            self.head.screen_from_world(context)
        if self.tail and self.tail.world_position:
            self.tail.screen_from_world(context)
        #if self.plane_tan.world_position:
            #self.plane_tan.screen_from_world(context)
            
        if debug > 1:
            if self.plane_com:
                com_2d = location_3d_to_region_2d(context.region, context.space_data.region_3d, self.plane_com)
                
                contour_utilities.draw_3d_points(context, [self.plane_com], (0,1,0,1), 4)
                if self.vec_x:
                    pt_x = location_3d_to_region_2d(context.region, context.space_data.region_3d, self.plane_com + self.vec_x)
                    screen_vec_x = pt_x - com_2d
                    screen_pt_x = com_2d + 40 * screen_vec_x.normalized()
                    contour_utilities.draw_points(context, [pt_x], (1,1,0,1), 6)
                    
                if self.vec_y:
                    pt_y = location_3d_to_region_2d(context.region, context.space_data.region_3d, self.plane_com + self.vec_y)
                    screen_vec_y = pt_y - com_2d
                    screen_pt_y = com_2d + 40 * screen_vec_y.normalized()
                    contour_utilities.draw_points(context, [pt_y], (0,1,1,1), 6)

                if self.plane_no:
                    pt_z = location_3d_to_region_2d(context.region, context.space_data.region_3d, self.plane_com + self.plane_no)
                    screen_vec_z = pt_z - com_2d
                    screen_pt_z = com_2d + 40 * screen_vec_z.normalized()
                    contour_utilities.draw_points(context, [pt_z], (1,0,1,1), 6)
                    
        
        #draw connecting line
        if self.head:
            points = [(self.head.x,self.head.y),(self.tail.x,self.tail.y)]
            
            contour_utilities.draw_polyline_from_points(context, points, self.stroke_color, settings.stroke_thick, "GL_LINE_STIPPLE")
        
            #draw the two handles
            contour_utilities.draw_points(context, points, self.head.color, settings.handle_size)
        
        #draw the current plane point and the handle to change plane orientation
        #if self.plane_pt and settings.draw_widget:
            #point1 = location_3d_to_region_2d(context.region, context.space_data.region_3d, self.plane_pt)
            #point2 = (self.plane_tan.x, self.plane_tan.y)

            #contour_utilities.draw_polyline_from_points(context, [point1,point2], (0,.2,1,1), settings.stroke_thick, "GL_LINE_STIPPLE")
            #contour_utilities.draw_points(context, [point2], self.plane_tan.color, settings.handle_size)
            #contour_utilities.draw_points(context, [point1], self.head.color, settings.handle_size)
        
        #draw the raw contour vertices
        if (self.verts and self.verts_simple == []) or (debug > 0 and settings.show_verts):
            
            if three_dimensional:
                
                contour_utilities.draw_3d_points(context, self.verts, self.vert_color, settings.raw_vert_size)
            else:    
                contour_utilities.draw_points(context, self.verts_screen, self.vert_color, settings.raw_vert_size)
        
        #draw the simplified contour vertices and edges (rings)    
        if self.verts !=[] and self.eds != []:
            if three_dimensional:
                points = self.verts_simple.copy()
            else:
                points = self.verts_simple_screen.copy()
               
            if 0 in self.eds[-1]:
                points.append(points[0])
            #draw the ring
            #draw the points over it
            if settings.show_ring_edges:
                if three_dimensional:
                    contour_utilities.draw_polyline_from_3dpoints(context, points, self.geom_color, settings.line_thick,"GL_LINE_STIPPLE")
                    if not interacting:
                        contour_utilities.draw_3d_points(context, points, self.vert_color, settings.vert_size)
                else:
                    contour_utilities.draw_polyline_from_points(context, points, self.geom_color, settings.line_thick,"GL_LINE_STIPPLE")
                    if not interacting:
                        contour_utilities.draw_points(context,points, self.vert_color, settings.vert_size)
                
            if debug:
                if settings.vert_inds:
                    for i, point in enumerate(self.verts):
                        loc = location_3d_to_region_2d(context.region, context.space_data.region_3d, point)
                        blf.position(0, loc[0], loc[1], 0)
                        blf.draw(0, str(i))
                    
                if settings.simple_vert_inds:    
                    for i, point in enumerate(self.verts_simple):
                        loc = location_3d_to_region_2d(context.region, context.space_data.region_3d, point)
                        blf.position(0, loc[0], loc[1], 0)
                        blf.draw(0, str(i))
    #draw contour points? later    
    def hit_object(self, context, ob, method = 'VIEW'):
        settings = context.user_preferences.addons['cgc-retopology'].preferences
        region = context.region  
        rv3d = context.space_data.region_3d
        
        pers_mx = rv3d.perspective_matrix  #we need the perspective matrix
        
        #the world direction vectors associated with
        #the view rotations
        view_x = rv3d.view_rotation * Vector((1,0,0))
        view_y = rv3d.view_rotation * Vector((0,1,0))
        view_z = rv3d.view_rotation * Vector((0,0,1))
        
        
        #this only happens on the first time.
        #after which everything is handled by
        #the widget
        if method == 'VIEW':
            #midpoint of the  cutline and world direction of cutline
            screen_coord = (self.head.x + self.tail.x)/2, (self.head.y + self.tail.y)/2
            cut_vec = (self.tail.x - self.head.x)*view_x + (self.tail.y - self.head.y)*view_y
            cut_vec.normalize()
            self.plane_no = cut_vec.cross(view_z).normalized()
            
            #we need to populate the 3 axis vectors
            self.vec_x = -1 * cut_vec.normalized()
            self.vec_y = self.plane_no.cross(self.vec_x)
            

    
            vec = region_2d_to_vector_3d(region, rv3d, screen_coord)
            loc = region_2d_to_location_3d(region, rv3d, screen_coord, vec)
    
            #raycast what I think is the ray onto the object
            #raycast needs to be in ob coordinates.
            a = loc + 3000*vec
            b = loc - 3000*vec

            mx = ob.matrix_world
            imx = mx.inverted()
            hit = ob.ray_cast(imx*a, imx*b)    
    
            if hit[2] != -1:
                self.head.world_position = region_2d_to_location_3d(region, rv3d, (self.head.x, self.head.y), mx * hit[0])
                self.tail.world_position = region_2d_to_location_3d(region, rv3d, (self.tail.x, self.tail.y), mx * hit[0])
                
                self.plane_pt = mx * hit[0]
                self.seed_face_index = hit[2]

                if settings.use_perspective:
                    
                    cut_vec = self.head.world_position - self.tail.world_position
                    cut_vec.normalize()
                    self.plane_no = cut_vec.cross(vec).normalized()
                    self.vec_x = -1 * cut_vec.normalized()
                    self.vec_y = self.plane_no.cross(self.vec_x)
                    

                    
                self.plane_x = self.plane_pt + self.vec_x
                self.plane_y = self.plane_pt + self.vec_y
                self.plane_z = self.plane_pt + self.plane_no
                    
                                #we need to populate the 3 axis vectors
            
            

                #self.plane_tan.world_position = self.plane_pt + self.vec_y
                
                
                
            else:
                self.plane_pt = None
                self.seed_face_index = None
                self.verts = []
                self.verts_simple = []
            
            return self.plane_pt
        
        elif method in {'3_AXIS_COM','3_AXIS_POINT'}:
            mx = ob.matrix_world
            imx = mx.inverted()
            y = self.vec_y
            x = self.vec_x
                  
            if method == '3_AXIS_COM':
                
                if not self.plane_com:
                    print('failed no COM')
                    return
                pt = self.plane_com


                
            else:
                if not self.plane_pt:
                    print('failed no COM')
                    return
                pt = self.plane_pt
                
            hits = [ob.ray_cast(imx * pt, imx * (pt + 5 * y)),
                    ob.ray_cast(imx * pt, imx * (pt + 5 * x)),
                    ob.ray_cast(imx * pt, imx * (pt - 5 * y)),
                    ob.ray_cast(imx * pt, imx * (pt - 5 * x))]
            

            dists = []
            inds = []
            for i, hit in enumerate(hits):
                if hit[2] != -1:
                    R = pt - hit[0]
                    dists.append(R.length)
                    inds.append(i)
            
            #make sure we had some hits!
            if any(dists):
                #pick the best one as the closest one to the pt       
                best_hit = hits[inds[dists.index(min(dists))]]       
                self.plane_pt = mx * best_hit[0]
                self.seed_face_index = best_hit[2]
                
                
            else:
                self.plane_pt = None
                self.seed_face_index = None
                self.verts = []
                self.verts_simple = []
                print('aim better')
                
            return self.plane_pt
            
    def handles_to_screen(self,context):
        
        region = context.region  
        rv3d = context.space_data.region_3d
        
        
        self.head.world_position = region_2d_to_location_3d(region, rv3d, (self.head.x, self.head.y),self.plane_pt)
        self.tail.world_position = region_2d_to_location_3d(region, rv3d, (self.tail.x, self.tail.y),self.plane_pt)
        
          
    def cut_object(self,context, ob, bme):
        
        mx = ob.matrix_world
        pt = self.plane_pt
        pno = self.plane_no
        indx = self.seed_face_index
        if pt and pno:
            cross = contour_utilities.cross_section_seed(bme, mx, pt, pno, indx, debug = True)   
            if cross:
                self.verts = [mx*v for v in cross[0]]
                self.eds = cross[1]
                
        else:
            self.verts = []
            self.eds = []
        
    def simplify_cross(self,segments):
        if self.verts !=[] and self.eds != []:
            [self.verts_simple, self.eds_simple] = contour_utilities.space_evenly_on_path(self.verts, self.eds, segments, self.shift)
            
            if self.int_shift:
                self.verts_simple = contour_utilities.list_shift(self.verts_simple, self.int_shift)
            
    def update_com(self):
        if self.verts_simple != []:
            self.plane_com = contour_utilities.get_com(self.verts_simple)
        else:
            self.plane_com = None
    
    def adjust_cut_to_object_surface(self,ob):
        
        vecs = []
        rot = ob.matrix_world.to_quaternion()
        for v in self.verts_simple:
            closest = ob.closest_point_on_mesh(v)  #this will be in local coords!
            
            s_no = closest[1]
            
            vecs.append(self.plane_com + s_no)
        
        print(self.plane_no)    
        (com, no) = contour_utilities.calculate_best_plane(vecs)
        
        #TODO add some sanity checks
    
        #first sanity check...keep normal in same dir
        if self.plane_no.dot(rot * no) < 0:
            no *= -1
        
        self.plane_no = rot * no
        
        
        
        
    
    def generic_3_axis_from_normal(self):
        
        (self.vec_x, self.vec_y) = contour_utilities.generic_axes_from_plane_normal(self.plane_com, self.plane_no)
        
                       
    def derive_3_axis_control(self, method = 'FROM_VECS', n=0):
        '''
        args
        
        method: text enum in {'VIEW','FROM_VECS','FROM_VERT'}
        '''
        
        if len(self.verts_simple) and self.plane_com:

            
            #y vector
            y_vector = self.verts_simple[n] - self.plane_com
            y_vector.normalize()
            self.vec_y = y_vector
            
            #x vector
            x_vector = y_vector.cross(self.plane_no)
            x_vector.normalize()
            self.vec_x = x_vector
            
            
            #now the 4 points are in world space
            #we could use a vector...but transforming
            #to screen can be tricky with vectors as
            #opposed to locations.
            self.plane_x = self.plane_com + x_vector
            self.plane_y = self.plane_com + y_vector
            self.plane_z = self.plane_com + self.plane_no
            
            
            
        
    def analyze_relationship(self, other,debug = False):
        '''
        runs a series of quantitative assemsents of the spatial relationship
        to another cut line to assist in anticipating the the optimized
        connectivity data
        
        assume the other cutline has already been solidified and the only variation
        which can happen is on this line
        '''
        #requirements
        # both loops must have a verts simple
        
        
        #caclulate the center of mass of each loop using existing
        #verts simple since they are evenly spaced it will be a
        #good example
        COM_other = contour_utilities.get_com(other.verts_simple)
        COM_self = contour_utilities.get_com(self.verts_simple)
        
        #the vector pointing from the COM of the other cutline
        #to this cutline.  This will be our convention for
        #positive direciton
        delta_com_vect = COM_self - COM_other  
        #delta_com_vect.normalize()
        
        #the plane normals
        self_no = self.plane_no.copy()
        other_no = other.plane_no.copy()
        
        #if for some reason they aren't normalized...fix that
        self_no.normalize()
        other_no.normalize()
        
        #make sure the other normal is aligned with
        #the line from other to self for convention
        if other_no.dot(delta_com_vect) < 0:
            other_no = -1 * other_no
            
        #and now finally make the self normal is aligned too    
        if self_no.dot(other_no) < 0:
            self_no = -1 * self_no
        
        #how parallel are the loops?
        parallelism = self_no.dot(other_no)
        if debug > 1:
            print('loop paralellism = %f' % parallelism)
        
        #this may be important.
        avg_no = self_no.lerp(other_no, 0.5)
        
        #are the loops aimed at one another?
        #compare the delta COM vector to each normal
        self_aimed_other = self_no.dot(delta_com_vect.normalized())
        other_aimed_self = other_no.dot(delta_com_vect.normalized())
        
        aiming_difference = self_aimed_other - other_aimed_self
        if debug > 1:
            print('aiming difference = %f' % aiming_difference)
        #do we expect divergence or convergence?
        #remember other -> self is positive so enlarging
        #while traveling in this direction is divergence
        radi_self = contour_utilities.approx_radius(self.verts_simple, COM_self)
        radi_other = contour_utilities.approx_radius(other.verts_simple, COM_other)
        
        #if divergent or convergent....we will want to maximize
        #the opposite phenomenon with respect to the individual
        #connectors and teh delta COM line
        divergent = (radi_self - radi_other) > 0
        divergence = (radi_self - radi_other)**2 / ((radi_self - radi_other)**2 + delta_com_vect.length**2)
        divergence = math.pow(divergence, 0.5)
        if debug > 1:
            print('the loops are divergent: ' + str(divergent) + ' with a divergence of: ' + str(divergence))
        
        return [COM_self, delta_com_vect, divergent, divergence]
        
    def connectivity_analysis(self,other):
        
        
        COM_self = contour_utilities.get_com(self.verts_simple)
        COM_other = contour_utilities.get_com(other.verts_simple)
        delta_com_vect = COM_self - COM_other  #final - initial :: self - other
        delta_com_vect.normalize()
        

        
        ideal_to_com = 0
        for i, v in enumerate(self.verts_simple):
            connector = v - other.verts_simple[i]  #continue convention of final - initial :: self - other
            connector.normalize()
            align = connector.dot(delta_com_vect)
            #this shouldnt happen but it appears to be...shrug
            if align < 0:
                print('damn reverse!')
                print(align)
                align *= -1    
            ideal_to_com += align
        
        ideal_to_com = 1/len(self.verts_simple) * ideal_to_com
        
        return ideal_to_com
        
        
    def align_to_other(self,other, auto_align = True, direction_only = False):
        
        '''
        Modifies vert order of self to  provide best
        bridge between self verts and other loop
        '''
        verts_1 = other.verts_simple
        
        eds_1 = other.eds_simple
        
        print('testing alignment')
        if 0 in eds_1[-1]:
            cyclic = True
            print('cyclic vert chain')
        else:
            cyclic = False
        
        if len(verts_1) != len(self.verts_simple):
            #print(len(verts_1))
            #print(len(self.verts_simple))
            print('non uniform loops, stopping until your developer gets smarter')
            return
        
        
        #turns out, sum of diagonals is > than semi perimeter
        #lets exploit this (only true if quad is pretty much flat)
        #if we have paths reversed...our indices will give us diagonals
        #instead of perimeter
        #D1_O = verts_2[0] - verts_1[0]
        #D2_O = verts_2[-1] - verts_1[-1]
        #D1_R = verts_2[0] - verts_1[-1]
        #D2_R = verts_2[-1] - verts_1[0]
                
        #original_length = D1_O.length + D2_O.length
        #reverse_length = D1_R.length + D2_R.length
        #if reverse_length < original_length:
            #verts_2.reverse()
            #print('reversing')
            
        if cyclic:
            #another test to verify loop direction is to take
            #something reminiscint of the curl
            #since the loops in our case are guaranteed planar
            #(they come from cross sections) we can find a direction
            #from which to take the curl pretty easily.  Apologies to
            #any real mathemeticians reading this becuase I just
            #bastardized all these math terms.
            V1_0 = verts_1[1] - verts_1[0]
            V1_1 = verts_1[2] - verts_1[1]
            
            V2_0 = self.verts_simple[1] - self.verts_simple[0]
            V2_1 = self.verts_simple[2] - self.verts_simple[1]
            
            no_1 = V1_0.cross(V1_1)
            no_1.normalize()
            no_2 = V2_0.cross(V2_1)
            no_2.normalize()
            
            #we have no idea which way we will get
            #so just pick the directions which are
            #pointed in the general same direction
            if no_1.dot(no_2) < 0:
                no_2 = -1 * no_2
            
            #average the two directions    
            ideal_direction = no_1.lerp(no_1,.5)
        
            curl_1 = contour_utilities.discrete_curl(verts_1, ideal_direction)
            curl_2 = contour_utilities.discrete_curl(self.verts_simple, ideal_direction)
            
            if curl_1 * curl_2 < 0:
                print('reversing derived loop direction')
                print('curl1: %f and curl2: %f' % (curl_1,curl_2))
                self.verts_simple.reverse()
                print('reversing the base loop')
                self.verts.reverse()
                self.shift *= -1
                
        
        else:
            #if the segement is not cyclic
            #all we have to do is compare the endpoints
            Vtotal_1 = verts_1[-1] - verts_1[0]
            Vtotal_2 = self.verts_simple[-1] - self.verts_simple[0]
    
            if Vtotal_1.dot(Vtotal_2) < 0:
                print('reversing path 2')
                self.verts_simple.reverse()
                self.verts.reverse()
                
        
        
        if not direction_only:
            #iterate all verts and "handshake problem" them
            #into a dictionary?  That's not very efficient!
            if auto_align:
                self.shift = 0
                self.int_shift = 0
                self.simplify_cross(len(self.eds_simple))
            edge_len_dict = {}
            for i in range(0,len(verts_1)):
                for n in range(0,len(self.verts_simple)):
                    edge = (i,n)
                    vect = self.verts_simple[n] - verts_1[i]
                    edge_len_dict[edge] = vect.length
            
            shift_lengths = []
            #shift_cross = []
            for shift in range(0,len(self.verts_simple)):
                tmp_len = 0
                #tmp_cross = 0
                for i in range(0, len(self.verts_simple)):
                    shift_mod = int(math.fmod(i+shift, len(self.verts_simple)))
                    tmp_len += edge_len_dict[(i,shift_mod)]
                shift_lengths.append(tmp_len)
                   
            final_shift = shift_lengths.index(min(shift_lengths))
            if final_shift != 0:
                print('pre rough shift alignment % f' % self.connectivity_analysis(other))
                print("rough shifting verts by %i segments" % final_shift)
                self.int_shift = final_shift
                self.verts_simple = contour_utilities.list_shift(self.verts_simple, final_shift)
                print('post rough shift alignment % f' % self.connectivity_analysis(other))
            
            if auto_align and cyclic:
                alignment_quality = self.connectivity_analysis(other)
                #pct_change = 1
                left_bound = -1
                right_bound = 1
                iterations = 0
                while iterations < 20:
                    
                    iterations += 1
                    width = right_bound - left_bound
                    
                    self.shift = 0.5 * (left_bound + right_bound)
                    self.simplify_cross(len(self.eds_simple)) #TODO not sure this needs to happen here
                    #self.verts_simple = contour_utilities.list_shift(self.verts_simple, final_shift)
                    alignment_quality = self.connectivity_analysis(other)
                    
                    self.shift = left_bound
                    self.simplify_cross(len(self.eds_simple))
                    #self.verts_simple = contour_utilities.list_shift(self.verts_simple, final_shift)
                    alignment_quality_left = self.connectivity_analysis(other)
                    
                    self.shift = right_bound
                    self.simplify_cross(len(self.eds_simple))
                    #self.verts_simple = contour_utilities.list_shift(self.verts_simple, final_shift)
                    alignment_quality_right = self.connectivity_analysis(other)
                    
                    if alignment_quality_left < alignment_quality and alignment_quality_right < alignment_quality:
                        
                        left_bound += width*1/8
                        right_bound -= width*1/8
                        
                        
                    elif alignment_quality_left > alignment_quality and alignment_quality_right > alignment_quality:
                        
                        if alignment_quality_right > alignment_quality_left:
                            left_bound = right_bound - 0.75 * width
                        else:
                            right_bound = left_bound + 0.75* width
                        
                    elif alignment_quality_left < alignment_quality and alignment_quality_right > alignment_quality:
                        #print('move to the right')
                        #right becomes the new middle
                        left_bound += width * 1/4
                
                    elif alignment_quality_left > alignment_quality and alignment_quality_right < alignment_quality:
                        #print('move to the left')
                        #right becomes the new middle
                        right_bound -= width * 1/4
                        
                        
                    #print('pct change iteration %i was %f' % (iterations, pct_change))
                    #print(alignment_quality)
                    #print(alignment_quality_left)
                    #print(alignment_quality_right)
                print('converged or didnt in %i iterations' % iterations)
                print('final alignment quality is %f' % alignment_quality)
              
    def active_element(self,context,x,y):
        settings = context.user_preferences.addons['cgc-retopology'].preferences
        
        if self.head: #this makes sure the head and tail haven't been removed
            active_head = self.head.mouse_over(x, y)
            active_tail = self.tail.mouse_over(x, y)
        else:
            active_head = False
            active_tail = False
        #active_tan = self.plane_tan.mouse_over(x, y)
        
        

        if len(self.verts_simple):
            mouse_loc = Vector((x,y))
            #Check by testing distance to all edges
            active_self = False
            for ed in self.eds_simple:
                
                a = self.verts_simple_screen[ed[0]]
                b = self.verts_simple_screen[ed[1]]
                intersect = intersect_point_line(mouse_loc, a, b)
        
                dist = (intersect[0] - mouse_loc).length_squared
                bound = intersect[1]
                if (dist < 100) and (bound < 1) and (bound > 0):
                    active_self = True
                    break
            
        else:
            active_self = False
            '''
            region = context.region  
            rv3d = context.space_data.region_3d
            vec = region_2d_to_vector_3d(region, rv3d, (x,y))
            loc = region_2d_to_location_3d(region, rv3d, (x,y), vec)
            
            line_a = loc
            line_b = loc + vec
            #ray to plane
            hit = intersect_line_plane(line_a, line_b, self.plane_pt, self.plane_no)
            if hit:
                mouse_in_loop = contour_utilities.point_inside_loop_almost3D(hit, self.verts_simple, self.plane_no, p_pt = self.plane_pt, threshold = .01, debug = False)
                if mouse_in_loop:
                    self.geom_color = (.8,0,.8,0.5)
                    self.line_width = 2.5 * settings.line_thick
                else:
                    self.geom_color = (0,1,0,0.5)
                    self.line_width = settings.line_thick
                
            
        mouse_loc = Vector((x,y,0))
        head_loc = Vector((self.head.x, self.head.y, 0))
        tail_loc = Vector((self.tail.x, self.tail.y, 0))
        intersect = intersect_point_line(mouse_loc, head_loc, tail_loc)
        
        dist = (intersect[0] - mouse_loc).length_squared
        bound = intersect[1]
        active_self = (dist < 100) and (bound < 1) and (bound > 0) #TODO:  make this a sensitivity setting
        '''
        #they are all clustered together
        if active_head and active_tail and active_self: 
            
            return self.head
        
        elif active_tail:
            #print('returning tail')
            return self.tail
        
        elif active_head:
            #print('returning head')
            return self.head
        
        #elif active_tan:
            #return self.plane_tan
        
        elif active_self:
            #print('returning line')
            return self
        
        else:
            #print('returning None')
            return None



class CutLineManipulatorWidget(object):
    def __init__(self,context, settings, cut_line,x,y,cut_line_a = None, cut_line_b = None, hotkey = False):
        
        self.desc = 'WIDGET'
        self.cut_line = cut_line
        self.x = x
        self.y = y
        self.hotkey = hotkey
        self.initial_x = None
        self.initial_y = None
        
        #this will get set later by interaction
        self.transform = False
        self.transform_mode = None
        
        if cut_line_a:
            self.a = cut_line_a.plane_com
            self.a_no = cut_line_a.plane_no
        else:
            self.a = None
            self.a_no = None
        
        if cut_line_b:
            self.b = cut_line_b.plane_com
            self.b_no = cut_line_b.plane_no
        else:
            self.b = None
            self.b_no = None
            
        self.color = (settings.widget_color[0], settings.widget_color[1],settings.widget_color[2],1)
        self.color2 = (settings.widget_color2[0], settings.widget_color2[1],settings.widget_color2[2],1)
        self.color3 = (settings.widget_color3[0], settings.widget_color3[1],settings.widget_color3[2],1)
        self.color4 = (settings.widget_color4[0], settings.widget_color4[1],settings.widget_color4[2],1)
        self.color5 = (settings.widget_color5[0], settings.widget_color5[1],settings.widget_color5[2],1)
        
        self.radius = settings.widget_radius
        self.inner_radius = settings.widget_radius_inner
        self.line_width = settings.widget_thickness
        self.line_width2 = settings.widget_thickness2
        self.arrow_size = settings.arrow_size
        
        self.arrow_size2 = settings.arrow_size2
        
        self.arc_radius = .5 * (self.radius + self.inner_radius)
        self.screen_no = None

        self.angle = 0
        
        #intitial conditions for "undo"
        if self.cut_line.plane_com:
            self.initial_com = self.cut_line.plane_com.copy()
        else:
            self.initial_com = None
            
        if self.cut_line.plane_pt:
            self.initial_plane_pt = self.cut_line.plane_pt.copy()
        else:
            self.initial_plane_pt = None
        
        self.vec_x = self.cut_line.vec_x.copy()
        self.vec_y = self.cut_line.vec_y.copy()
        self.initial_plane_no = self.cut_line.plane_no.copy()
        self.initial_seed = self.cut_line.seed_face_index
        
        self.wedge_1 = []
        self.wedge_2 = []
        self.wedge_3 = []
        self.wedge_4 = []
        
        self.arrow_1 = []
        self.arrow_2 = []
        
        self.arc_arrow_1 = []
        self.arc_arrow_2 = []
        

        
    def user_interaction(self, context, mouse_x,mouse_y):
        '''
        analyse mouse coords x,y
        return [type, transform]
        '''
        
        mouse_vec = Vector((mouse_x,mouse_y))
        
        
        #In hotkey mode G, this will be spawned at the mouse
        #essentially being the initial mouse
        widget_screen = Vector((self.x,self.y))
        mouse_wrt_widget = mouse_vec - widget_screen
        com_screen = location_3d_to_region_2d(context.region, context.space_data.region_3d,self.initial_com)
        
        
        region = context.region
        rv3d = context.space_data.region_3d
        world_mouse = region_2d_to_location_3d(region, rv3d, (mouse_x, mouse_y), self.initial_com)
        world_widget = region_2d_to_location_3d(region, rv3d, (self.x, self.y), self.initial_com)
        
        if not self.transform and not self.hotkey:
            #this represents a switch...since by definition we were not transforming to begin with
            if mouse_wrt_widget.length > self.inner_radius:
                self.transform = True
                
                #identify which quadrant we are in
                screen_angle = math.atan2(mouse_wrt_widget[1], mouse_wrt_widget[0])
                loc_angle = screen_angle - self.angle
                loc_angle = math.fmod(loc_angle + 4 * math.pi, 2 * math.pi)  #correct for any negatives
                
                if loc_angle >= 1/4 * math.pi and loc_angle < 3/4 * math.pi:
                    #we are in the  left quadrant...which is perpendicular
                    self.transform_mode = 'EDGE_SLIDE'
                    
                elif loc_angle >= 3/4 * math.pi and loc_angle < 5/4 * math.pi:
                    self.transform_mode = 'ROTATE_VIEW'
                
                elif loc_angle >= 5/4 * math.pi and loc_angle < 7/4 * math.pi:
                    self.transform_mode = 'EDGE_SLIDE'
                
                else:
                    self.transform_mode = 'ROTATE_VIEW_PERPENDICULAR'
                    

                #print(loc_angle)
                print(self.transform_mode)
                
            return {'DO_NOTHING'}  #this tells it whether to recalc things
            
        else:
            #we were transforming but went back in the circle
            if mouse_wrt_widget.length < self.inner_radius and not self.hotkey:
                
                self.cancel_transform()
                self.transform = False
                self.transform_mode = None
                
                
                
                return {'RECUT'}
                
            
            else:
                
                if self.transform_mode == 'EDGE_SLIDE':
                    
                    world_vec = world_mouse - world_widget
                    screen_dist = mouse_wrt_widget.length - self.inner_radius
                    
                    print(screen_dist)
                    
                    if self.hotkey:
                        factor =  1
                    else:
                        factor = screen_dist/mouse_wrt_widget.length
                    
                    
                    if self.a:
                        a_screen = location_3d_to_region_2d(context.region, context.space_data.region_3d,self.a)
                        vec_a_screen = a_screen - com_screen
                        vec_a_screen_norm = vec_a_screen.normalized()
                        
                        vec_a = self.a - self.initial_com
                        vec_a_dir = vec_a.normalized()
                        
                        
                        if mouse_wrt_widget.dot(vec_a_screen_norm) > 0 and factor * mouse_wrt_widget.dot(vec_a_screen_norm) < vec_a_screen.length:
                            translate = factor * mouse_wrt_widget.dot(vec_a_screen_norm)/vec_a_screen.length * vec_a
                            
                            if self.a_no.dot(self.initial_plane_no) < 0:
                                v = -1 * self.a_no
                            else:
                                v = self.a_no
                            
                            scale = factor * mouse_wrt_widget.dot(vec_a_screen_norm)/vec_a_screen.length
                            quat = contour_utilities.rot_between_vecs(self.initial_plane_no, v, factor = scale)
                            inter_no = quat * self.initial_plane_no
                            
                            self.cut_line.plane_com = self.initial_com + translate
                            self.cut_line.plane_no = inter_no
                            
                            self.cut_line.vec_x = quat * self.vec_x.copy()
                            self.cut_line.vec_y = quat * self.vec_y.copy()
                            
                            return {'REHIT','RECUT'}
                        
                        elif not self.b and world_vec.dot(vec_a_dir) < 0:
                            translate = factor * world_vec.dot(self.initial_plane_no) * self.initial_plane_no
                            self.cut_line.plane_com = self.initial_com + translate
                            return {'REHIT','RECUT'}
                        
                        
                    if self.b:
                        b_screen = location_3d_to_region_2d(context.region, context.space_data.region_3d,self.b)
                        vec_b_screen = b_screen - com_screen
                        vec_b_screen_norm = vec_b_screen.normalized()
                        
                        vec_b = self.b - self.initial_com
                        vec_b_dir = vec_b.normalized()
                        
                        
                        if mouse_wrt_widget.dot(vec_b_screen_norm) > 0 and factor * mouse_wrt_widget.dot(vec_b_screen_norm) < vec_b_screen.length:
                            translate = factor * mouse_wrt_widget.dot(vec_b_screen_norm)/vec_b_screen.length * vec_b
                            
                            if self.b_no.dot(self.initial_plane_no) < 0:
                                v = -1 * self.b_no
                            else:
                                v = self.b_no
                            
                            scale = factor * mouse_wrt_widget.dot(vec_b_screen_norm)/vec_b_screen.length
                            quat = contour_utilities.rot_between_vecs(self.initial_plane_no, v, factor = scale)
                            inter_no = quat * self.initial_plane_no
                            
                            self.cut_line.plane_com = self.initial_com + translate
                            self.cut_line.plane_no = inter_no
                            self.cut_line.vec_x = quat * self.vec_x.copy()
                            self.cut_line.vec_y = quat * self.vec_y.copy()
                            return {'REHIT','RECUT'}
                            
                        
                        elif not self.a and world_vec.dot(vec_b_dir) < 0:
                            translate = factor * world_vec.dot(self.initial_plane_no) * self.initial_plane_no
                            self.cut_line.plane_com = self.initial_com + translate
                            
                    if not self.a and not self.b:
                        translate = factor * world_vec.dot(self.initial_plane_no) * self.initial_plane_no
                        self.cut_line.plane_com = self.initial_com + translate
                        return {'REHIT','RECUT'}
                    
                    return {'DO_NOTHING'}

                    
                if self.transform_mode == 'NORMAL_TRANSLATE':
                    print('translating')
                    #the pixel distance used to scale the translation
                    screen_dist = mouse_wrt_widget.length - self.inner_radius
                    
                    world_vec = world_mouse - world_widget
                    translate = screen_dist/mouse_wrt_widget.length * world_vec.dot(self.initial_plane_no) * self.initial_plane_no
                    
                    self.cut_line.plane_com = self.initial_com + translate
                    
                    return {'REHIT','RECUT'}
                
                elif self.transform_mode in {'ROTATE_VIEW_PERPENDICULAR', 'ROTATE_VIEW'}:
                    
                    #establish the transform axes
                    '''
                    screen_com = location_3d_to_region_2d(context.region, context.space_data.region_3d,self.cut_line.plane_com)
                    vertical_screen_vec = Vector((math.cos(self.angle + .5 * math.pi), math.sin(self.angle + .5 * math.pi)))
                    screen_y = screen_com + vertical_screen_vec
                    world_pre_y = region_2d_to_location_3d(region, rv3d, (screen_y[0], screen_y[1]),self.cut_line.plane_com)
                    world_y = world_pre_y - self.cut_line.plane_com
                    world_y_correct = world_y.dot(self.initial_plane_no)
                    world_y = world_y - world_y_correct * self.initial_plane_no
                    world_y.normalize()
                    
                    world_x = self.initial_plane_no.cross(world_y)
                    world_x.normalize()
                    '''
                    
                    axis_1  = rv3d.view_rotation * Vector((0,0,1))
                    axis_1.normalize()
                    
                    axis_2 = self.initial_plane_no.cross(axis_1)
                    axis_2.normalize()
                    
                    #self.cut_line.vec_x = world_x
                    #self.cut_line.vec_y = world_y
                    
                    #self.cut_line.plane_x = self.cut_line.plane_com + 2 * world_x
                    #self.cut_line.plane_y = self.cut_line.plane_com + 2 * world_y
                    #self.cut_line.plane_z = self.cut_line.plane_com + 2 * self.initial_plane_no
                    
                    #identify which quadrant we are in
                    screen_angle = math.atan2(mouse_wrt_widget[1], mouse_wrt_widget[0])
                    
                    if self.transform_mode == 'ROTATE_VIEW':
                        if not self.hotkey:
                            rot_angle = screen_angle - self.angle #+ .5 * math.pi  #Mystery
                            
                        else:
                            init_angle = math.atan2(self.initial_y - self.y, self.initial_x - self.x)
                            init_angle = math.fmod(init_angle + 4 * math.pi, 2 * math.pi)
                            rot_angle = screen_angle - init_angle
                            
                        rot_angle = math.fmod(rot_angle + 4 * math.pi, 2 * math.pi)  #correct for any negatives
                        print('rotating by %f' % rot_angle)
                        sin = math.sin(rot_angle/2)
                        cos = math.cos(rot_angle/2)
                        #quat = Quaternion((cos, sin*world_x[0], sin*world_x[1], sin*world_x[2]))
                        quat = Quaternion((cos, sin*axis_1[0], sin*axis_1[1], sin*axis_1[2]))


                    
                    else:
                        rot_angle = screen_angle - self.angle + math.pi #+ .5 * math.pi  #Mystery
                        rot_angle = math.fmod(rot_angle + 4 * math.pi, 2 * math.pi)  #correct for any negatives
                        print('rotating by %f' % rot_angle)
                        sin = math.sin(rot_angle/2)
                        cos = math.cos(rot_angle/2)
                        #quat = Quaternion((cos, sin*world_y[0], sin*world_y[1], sin*world_y[2]))
                        quat = Quaternion((cos, sin*axis_2[0], sin*axis_2[1], sin*axis_2[2])) 
                        
                        #new_no = self.initial_plane_no.copy() #its not rotated yet
                        #new_no.rotate(quat)
    
                        #rotate around x axis...update y
                        #world_x = world_y.cross(new_no)
                        #new_com = self.initial_com
                        #new_tan = new_com + world_x
                        
                        
                        #self.cut_line.plane_x = self.cut_line.plane_com + 2 * world_x
                        #self.cut_line.plane_y = self.cut_line.plane_com + 2 * world_y
                        #self.cut_line.plane_z = self.cut_line.plane_com + 2 * new_no
                    
               
                    new_no = self.initial_plane_no.copy() #its not rotated yet
                    new_no.rotate(quat)

                    new_x = self.vec_x.copy() #its not rotated yet
                    new_x.rotate(quat)
                   
                    new_y = self.vec_y.copy()
                    new_y.rotate(quat)
                    
                    self.cut_line.vec_x = new_x
                    self.cut_line.vec_y = new_y
                    self.cut_line.plane_no = new_no    
                    return {'RECUT'}
        
        #
        #Tranfsorm mode = NORMAL_TANSLATE
            #get the distance from mouse to self.x,y - inner radius
            
            #get the world distance by projecting both the original x,y- inner radius
            #and the mouse_x,mouse_y to the depth of the COPM
            
            #if "precision divide by 1/10?
            
            #add the translation vector to the
        
        #Transform mode = ROTATE_VIEW
        
        #Transfrom mode = EDGE_PEREPENDICULAR
        

    def derive_screen(self,context):
        rv3d = context.space_data.region_3d
        view_z = rv3d.view_rotation * Vector((0,0,1))
        if view_z.dot(self.initial_plane_no) > -.95 and view_z.dot(self.initial_plane_no) < .95:
            #point_0 = location_3d_to_region_2d(context.region, context.space_data.region_3d,self.cut_line.plane_com)
            #point_1 = location_3d_to_region_2d(context.region, context.space_data.region_3d,self.cut_line.plane_com + self.initial_plane_no.normalized())
            #self.screen_no = point_1 - point_0
            #if self.screen_no.dot(Vector((0,1))) < 0:
                #self.screen_no = point_0 - point_1
            #self.screen_no.normalize()
            
            imx = rv3d.view_matrix.inverted()
            normal_3d = imx.transposed() * self.cut_line.plane_no
            self.screen_no = Vector((normal_3d[0],normal_3d[1]))
            
            self.angle = math.atan2(self.screen_no[1],self.screen_no[0]) - 1/2 * math.pi
        else:
            self.screen_no = None
        
        
        up = self.angle + 1/2 * math.pi
        down = self.angle + 3/2 * math.pi
        left = self.angle + math.pi
        right =  self.angle
        
        deg_45 = .25 * math.pi
        
        self.wedge_1 = contour_utilities.pi_slice(self.x,self.y,self.inner_radius,self.radius,up - deg_45,up + deg_45, 10 ,t_fan = False)
        self.wedge_2 = contour_utilities.pi_slice(self.x,self.y,self.inner_radius,self.radius,left - deg_45,left + deg_45, 10 ,t_fan = False)
        self.wedge_3 = contour_utilities.pi_slice(self.x,self.y,self.inner_radius,self.radius,down - deg_45,down + deg_45, 10 ,t_fan = False)
        self.wedge_4 = contour_utilities.pi_slice(self.x,self.y,self.inner_radius,self.radius,right - deg_45,right + deg_45, 10 ,t_fan = False)
        self.wedge_1.append(self.wedge_1[0])
        self.wedge_2.append(self.wedge_2[0])
        self.wedge_3.append(self.wedge_3[0])
        self.wedge_4.append(self.wedge_4[0])
        
        
        self.arc_arrow_1 = contour_utilities.arc_arrow(self.x, self.y, self.arc_radius, left - deg_45+.2, left + deg_45-.2, 10, self.arrow_size, 2*deg_45, ccw = True)
        self.arc_arrow_2 = contour_utilities.arc_arrow(self.x, self.y, self.arc_radius, right - deg_45+.2, right + deg_45-.2, 10, self.arrow_size,2*deg_45, ccw = True)
  
        self.inner_circle = contour_utilities.simple_circle(self.x, self.y, self.inner_radius, 20)
        
        #New screen coords, leaving old ones until completely transitioned
        self.arc_arrow_rotate_ccw = contour_utilities.arc_arrow(self.x, self.y, self.radius, left - deg_45-.3, left + deg_45+.3, 10, self.arrow_size, 2*deg_45, ccw = True)
        self.arc_arrow_rotate_cw = contour_utilities.arc_arrow(self.x, self.y, self.radius, left - deg_45-.3, left + deg_45+.3, 10, self.arrow_size, 2*deg_45, ccw = False)
        
        self.inner_circle = contour_utilities.simple_circle(self.x, self.y, self.inner_radius, 20)
        self.inner_circle.append(self.inner_circle[0])
        
        self.outer_circle_1 = contour_utilities.arc_arrow(self.x, self.y, self.radius, up, down,10, self.arrow_size,2*deg_45, ccw = True)
        self.outer_circle_2 = contour_utilities.arc_arrow(self.x, self.y, self.radius, down, up,10, self.arrow_size,2*deg_45, ccw = True)
        
        b = self.arrow_size2
        self.trans_arrow_up = contour_utilities.arrow_primitive(self.x +math.cos(up) * self.radius, self.y + math.sin(up)*self.radius, right, b, b, b, b/2)
        self.trans_arrow_down = contour_utilities.arrow_primitive(self.x + math.cos(down) * self.radius, self.y + math.sin(down) * self.radius, left, b, b, b, b/2)
    
    def cancel_transform(self):
        
        #reset our initial values
        self.cut_line.plane_com = self.initial_com
        self.cut_line.plane_no = self.initial_plane_no
        self.cut_line.plane_pt = self.initial_plane_pt
        self.cut_line.vec_x = self.vec_x
        self.cut_line.vec_y = self.vec_y
        self.cut_line.seed_face_index = self.initial_seed
                
                  
    def draw(self, context):
        
        settings = context.user_preferences.addons['cgc-retopology'].preferences
        
        if self.a:
            contour_utilities.draw_3d_points(context, [self.a], self.color3, 5)
        if self.b:
            contour_utilities.draw_3d_points(context, [self.b], self.color3, 5)
            
            
        if not self.transform and not self.hotkey:
            #draw wedges
            #contour_utilities.draw_polyline_from_points(context, self.wedge_1, self.color, self.line_width, "GL_LINES")
            #contour_utilities.draw_polyline_from_points(context, self.wedge_2, self.color, self.line_width, "GL_LINES")
            #contour_utilities.draw_polyline_from_points(context, self.wedge_3, self.color, self.line_width, "GL_LINES")
            #contour_utilities.draw_polyline_from_points(context, self.wedge_4, self.color, self.line_width, "GL_LINES")
            
            #draw inner circle
            #contour_utilities.draw_polyline_from_points(context, self.inner_circle, (self.color[0],self.color[1],self.color[2],.5), self.line_width, "GL_LINES")
            
            #draw outer circle (two halfs later)
            #contour_utilities.draw_polyline_from_points(context, self.outer_circle_1[0:l-1], (0,.5,.8,1), self.line_width, "GL_LINES")

                
            #draw arc 1
            l = len(self.arc_arrow_1)
            #contour_utilities.draw_polyline_from_points(context, self.arc_arrow_1[:l-1], self.color2, self.line_width, "GL_LINES")

            #draw outer circle half
            contour_utilities.draw_polyline_from_points(context, self.outer_circle_1[0:l-2], self.color4, self.line_width, "GL_LINES")
            contour_utilities.draw_polyline_from_points(context, self.outer_circle_2[0:l-2], self.color4, self.line_width, "GL_LINES")
            
            #draw outer translation arrows
            #contour_utilities.draw_polyline_from_points(context, self.trans_arrow_up, self.color3, self.line_width, "GL_LINES")
            #contour_utilities.draw_polyline_from_points(context, self.trans_arrow_down, self.color3, self.line_width, "GL_LINES")            
            
            
            contour_utilities.draw_outline_or_region("GL_POLYGON", self.trans_arrow_down[:4], self.color3)
            contour_utilities.draw_outline_or_region("GL_POLYGON", self.trans_arrow_up[:4], self.color3)
            contour_utilities.draw_outline_or_region("GL_POLYGON", self.trans_arrow_down[4:], self.color3)
            contour_utilities.draw_outline_or_region("GL_POLYGON", self.trans_arrow_up[4:], self.color3)
            
            #draw a line perpendicular to arc
            #point_1 = Vector((self.x,self.y)) + 2/3 * (self.inner_radius + self.radius) * Vector((math.cos(self.angle), math.sin(self.angle)))
            #point_2 = Vector((self.x,self.y)) + 1/3 * (self.inner_radius + self.radius) * Vector((math.cos(self.angle), math.sin(self.angle)))
            #contour_utilities.draw_polyline_from_points(context, [point_1, point_2], self.color3, self.line_width, "GL_LINES")
            
            
            #try the straight red line
            point_1 = Vector((self.x,self.y)) #+ self.inner_radius * Vector((math.cos(self.angle), math.sin(self.angle)))
            point_2 = Vector((self.x,self.y)) +  self.radius * Vector((math.cos(self.angle), math.sin(self.angle)))
            contour_utilities.draw_polyline_from_points(context, [point_1, point_2], self.color2, self.line_width2 , "GL_LINES")
            
            point_1 = Vector((self.x,self.y))# + -self.inner_radius * Vector((math.cos(self.angle), math.sin(self.angle)))
            point_2 = Vector((self.x,self.y)) +  -self.radius * Vector((math.cos(self.angle), math.sin(self.angle)))
            contour_utilities.draw_polyline_from_points(context, [point_1, point_2], self.color2, self.line_width, "GL_LINES")
            
            #drawa arc 2
            #contour_utilities.draw_polyline_from_points(context, self.arc_arrow_2[:l-1], self.color2, self.line_width, "GL_LINES")
            
            #new rotation thingy
            contour_utilities.draw_polyline_from_points(context, self.arc_arrow_rotate_ccw[:l-1], self.color, self.line_width2, "GL_LINES")
            contour_utilities.draw_polyline_from_points(context, self.arc_arrow_rotate_cw[:l-1], self.color, self.line_width2, "GL_LINES")
            
            #other half the tips
            contour_utilities.draw_polyline_from_points(context, [self.arc_arrow_rotate_ccw[l-1],self.arc_arrow_rotate_ccw[l-3]], (0,0,1,1), self.line_width2, "GL_LINES")
            contour_utilities.draw_polyline_from_points(context, [self.arc_arrow_rotate_cw[l-1],self.arc_arrow_rotate_cw[l-3]], (0,0,1,1), self.line_width2, "GL_LINES")
            
            #draw an up and down arrow
            #point_1 = Vector((self.x,self.y)) + 2/3 * (self.inner_radius + self.radius) * Vector((math.cos(self.angle + .5*math.pi), math.sin(self.angle + .5*math.pi)))
            #point_2 = Vector((self.x,self.y)) + 1/3 * (self.inner_radius + self.radius) * Vector((math.cos(self.angle + .5*math.pi), math.sin(self.angle + .5*math.pi)))
            #contour_utilities.draw_polyline_from_points(context, [point_1, point_2], self.color, self.line_width, "GL_LINES")
            
            #draw little hash
            #point_1 = Vector((self.x,self.y)) + 2/3 * (self.inner_radius + self.radius) * Vector((math.cos(self.angle +  3/2 * math.pi), math.sin(self.angle +  3/2 * math.pi)))
            #point_2 = Vector((self.x,self.y)) + 1/3 * (self.inner_radius + self.radius) * Vector((math.cos(self.angle +  3/2 * math.pi), math.sin(self.angle +  3/2 * math.pi)))
            #contour_utilities.draw_polyline_from_points(context, [point_1, point_2], self.color, self.line_width, "GL_LINES")
        
        elif self.transform_mode:

            #draw a small inner circle
            contour_utilities.draw_polyline_from_points(context, self.inner_circle, self.color, self.line_width, "GL_LINES")
            
            
            if not settings.live_update:
                if self.transform_mode in {"NORMAL_TRANSLATE", "EDGE_SLIDE"}:
                    #draw a line representing the COM translation
                    points = [self.initial_com, self.cut_line.plane_com]
                    contour_utilities.draw_3d_points(context, points, self.color3, 4)
                    contour_utilities.draw_polyline_from_3dpoints(context, points, self.color ,2 , "GL_STIPPLE")
                    
                else:
                    rv3d = context.space_data.region_3d

                    p1 = self.cut_line.plane_com
                    p1_2d =  location_3d_to_region_2d(context.region, context.space_data.region_3d, p1)
                    #p2_2d =  location_3d_to_region_2d(context.region, context.space_data.region_3d, p2)
                    #p3_2d =  location_3d_to_region_2d(context.region, context.space_data.region_3d, p3)
                    
                    
                    imx = rv3d.view_matrix.inverted()
                    vec_screen = imx.transposed() * self.cut_line.plane_no
                    vec_2d = Vector((vec_screen[0],vec_screen[1]))

                    p4_2d = p1_2d + self.radius * vec_2d
                    p6_2d = p1_2d - self.radius * vec_2d
                    
                    print('previewing the rotation')
                    contour_utilities.draw_points(context, [p1_2d, p4_2d, p6_2d], self.color3, 5)
                    contour_utilities.draw_polyline_from_points(context, [p6_2d, p4_2d], self.color ,2 , "GL_STIPPLE")
            
            
            #If self.transform_mode != 
#cut line, a user interactive 2d line which represents a plane in 3d splace
    #head (type conrol point)
    #tail (type control points)
    #target mesh
    #view_direction (crossed with line to make plane normal for slicing)
    
    #draw method
    
    #new control point project method
    
    #mouse hover line calc
    
    
#retopo object, surface
    #colelction of cut lines
    #collection of countours to loft
    
    #n rings (crosses borrowed from looptools)
    #n follows (borrowed from looptools and or bsurfaces)
    
    #method contours from cutlines
    
    #method bridge contours