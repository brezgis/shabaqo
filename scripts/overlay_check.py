import cv2, json, sys, numpy as np
cv2.setNumThreads(4)
P="/home/anna/projects/shabaka-stone/"
H=np.array(json.load(open(P+"work/H_plate_to_photo.json"))["H"])
plate=cv2.imread(P+"work/breasted_plate_mask.png",0); plate[2345:]=0; plate[:,3755:]=0
photo=cv2.imread(P+"raw/commons_11448.jpg")
out=sys.argv[1]
if len(sys.argv)>2:
    F=np.load(P+"work/disp_field.npz"); f=int(F["f"])
    Hh,Ww=plate.shape
    dx=cv2.resize(F["dx"],(Ww,Hh),interpolation=cv2.INTER_LINEAR); dy=cv2.resize(F["dy"],(Ww,Hh),interpolation=cv2.INTER_LINEAR)
    gy,gx=np.mgrid[0:Hh,0:Ww].astype(np.float32)
    plate=cv2.remap(plate,gx-dx,gy-dy,cv2.INTER_LINEAR)
for name,(x0,y0,x1,y1),k in [("ov_all",(0,0,11448,7452),0.14),("ov_left",(900,1200,3600,3700),0.33),("ov_right",(8200,3500,10900,6000),0.33),("ov_mid",(4600,1300,7600,4800),0.3)]:
    T=np.diag([k,k,1])@np.array([[1,0,-x0],[0,1,-y0],[0,0,1]])@H
    w,h=int((x1-x0)*k),int((y1-y0)*k)
    ink=cv2.warpPerspective(plate,T,(w,h),flags=cv2.INTER_AREA)
    ph=cv2.resize(photo[y0:y1,x0:x1],(w,h),interpolation=cv2.INTER_AREA)
    ph=cv2.createCLAHE(3,(8,8)).apply(cv2.cvtColor(ph,cv2.COLOR_BGR2GRAY)); ph=cv2.cvtColor(ph,cv2.COLOR_GRAY2BGR)
    m=ink>60; ph[m]=(0.3*ph[m]+[0,0,180]).astype(np.uint8)
    cv2.imwrite(f"{out}/{name}{sys.argv[2] if len(sys.argv)>2 else ''}.png",ph)
