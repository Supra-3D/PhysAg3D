import numpy as np,math

def tube_between(B,name,a,b,r,owner,mat,collision=False):
 a,b=np.array(a,float),np.array(b,float);o=B.cylinder(name,r,float(np.linalg.norm(b-a)),(a+b)/2,b-a,owner,mat)
 if collision:B.capsule(owner,a,b,r)
 return o

def lathe_y(B,name,center,profile,owner,mat,steps=96):
 center=np.array(center,float);verts=[];faces=[]
 for radial,offset in profile:
  for i in range(steps):
   t=2*math.pi*i/steps;verts.append(center+[radial*math.cos(t),offset,radial*math.sin(t)])
 for j in range(len(profile)):
  for i in range(steps):faces.append([j*steps+i,j*steps+(i+1)%steps,((j+1)%len(profile))*steps+(i+1)%steps,((j+1)%len(profile))*steps+i])
 return B.mesh(name,np.array(verts),np.array(faces),owner,mat)

def shell_loft_x(B,name,xs,center_y,zbase,depth,height,thickness,owner,mat,steps=36):
 verts=[];faces=[];n=steps+1
 for x in xs:
  for inner in [False,True]:
   for i in range(n):
    t=math.pi*i/steps;ry=depth/2-(thickness if inner else 0);rz=height-(thickness if inner else 0)
    verts.append([x,center_y+ry*math.cos(t),zbase+rz*math.sin(t)])
 for j in range(len(xs)-1):
  for inner in [0,1]:
   for i in range(steps):
    a=j*2*n+inner*n+i;b=(j+1)*2*n+inner*n+i
    face=[a,a+1,b+1,b];faces.append(face[::-1] if inner else face)
 for j in [0,len(xs)-1]:
  for i in range(steps):a=j*2*n+i;faces.append([a,a+1,a+1+n,a+n])
 for j in range(len(xs)-1):
  for i in [0,steps]:a=j*2*n+i;b=(j+1)*2*n+i;faces.append([a,b,b+n,a+n])
 return B.mesh(name,np.array(verts),np.array(faces),owner,mat)
