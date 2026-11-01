"""Time-aware continuous curves for explicitly flowing keyframe segments.

Settling/hold segments retain existing easing. Only ``flow`` opts into shared
endpoint velocities. Closed loops use periodic neighbours, not endpoint stops.
"""
from __future__ import annotations

import numpy as np


def neighbours(times, values, index, loop, duration):
    n = len(times)
    closed = loop and n > 2 and abs(float(times[0])) < 1e-6 and abs(float(times[-1])-duration) < 1e-5
    if index == 0:
        if closed:
            return n-2, float(times[n-2])-duration, 1, float(times[1])
        return None
    if index == n-1:
        if closed:
            return n-2, float(times[n-2]), 1, duration+float(times[1])
        return None
    return index-1, float(times[index-1]), index+1, float(times[index+1])


def vector_tangent(times, values, index, loop, duration):
    adjacent = neighbours(times, values, index, loop, duration)
    if adjacent is None:
        return np.zeros_like(values[index], dtype=np.float64)
    a, ta, b, tb = adjacent
    t = float(times[index])
    before = (np.asarray(values[index])-values[a])/max(1e-8,t-ta)
    after = (np.asarray(values[b])-values[index])/max(1e-8,tb-t)
    # Shape-preserving harmonic mean: extrema stop, same-direction keys pass.
    same = before*after > 0
    denom = before+after
    result = np.zeros_like(np.asarray(values[index]), dtype=np.float64)
    np.divide(2*before*after, denom, out=result, where=same & (abs(denom)>1e-12))
    return result


def hermite(a,b,va,vb,u,span):
    u2=u*u; u3=u2*u
    return (2*u3-3*u2+1)*a+(u3-2*u2+u)*span*va+(-2*u3+3*u2)*b+(u3-u2)*span*vb


def multiply(a,b):
    av=np.asarray(a[:3]); bv=np.asarray(b[:3])
    return np.r_[a[3]*bv+b[3]*av+np.cross(av,bv), a[3]*b[3]-np.dot(av,bv)]


def log_delta(a,b):
    a=np.asarray(a,dtype=np.float64); b=np.asarray(b,dtype=np.float64)
    if np.dot(a,b)<0: b=-b
    relative=multiply(np.r_[-a[:3],a[3]],b)
    length=float(np.linalg.norm(relative[:3]))
    if length<1e-10: return np.zeros(3)
    return relative[:3]*(np.arctan2(length,relative[3])/length)


def exp_delta(v):
    length=float(np.linalg.norm(v))
    if length<1e-10: return np.r_[v,1.0]
    return np.r_[v*np.sin(length)/length,np.cos(length)]


def quaternion_tangent(times, values, index, loop, duration):
    adjacent=neighbours(times,values,index,loop,duration)
    if adjacent is None: return np.zeros(3)
    a,ta,b,tb=adjacent; t=float(times[index]); q=values[index]
    before=-log_delta(q,values[a])/max(1e-8,t-ta)
    after=log_delta(q,values[b])/max(1e-8,tb-t)
    # Holds and reversals are intentional rests; a neighbouring gesture must
    # not cause a constant segment to wander away from its support pose.
    if np.linalg.norm(before)<1e-9 or np.linalg.norm(after)<1e-9 or np.dot(before,after)<=0:
        return np.zeros(3)
    return (before*(tb-t)+after*(t-ta))/max(1e-8,tb-ta)


def spherical_cubic(a,b,va,vb,u,span,slerp):
    c=multiply(a,exp_delta(va*span/3))
    d=multiply(b,exp_delta(-vb*span/3))
    ab=slerp(a,c,u); bc=slerp(c,d,u); cd=slerp(d,b,u)
    return slerp(slerp(ab,bc,u),slerp(bc,cd,u),u)
