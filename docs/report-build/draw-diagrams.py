"""Draw project-specific engineering models, distinct from operational evidence."""
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / 'report-assets'
FONT = 'C:/Windows/Fonts/calibri.ttf'
BOLD = 'C:/Windows/Fonts/calibrib.ttf'

def diagram(name, title, nodes, edges, width=1800, height=1100):
    image=Image.new('RGB',(width,height),'white'); d=ImageDraw.Draw(image)
    d.text((50,25),title,font=ImageFont.truetype(BOLD,42),fill='#17365D')
    d.text((50,height-45),'Engineering model of the implemented project',font=ImageFont.truetype(FONT,24),fill='#5B6573')
    positions={n[0]:n[1:5] for n in nodes}
    for source,target,label in edges:
        a=positions[source];b=positions[target]
        ax,ay=a[0]+a[2]/2,a[1]+a[3]/2;bx,by=b[0]+b[2]/2,b[1]+b[3]/2
        vx,vy=bx-ax,by-ay
        sa=min(a[2]/2/abs(vx) if vx else 999,a[3]/2/abs(vy) if vy else 999)
        sb=min(b[2]/2/abs(vx) if vx else 999,b[3]/2/abs(vy) if vy else 999)
        start=(ax+vx*sa,ay+vy*sa);end=(bx-vx*sb,by-vy*sb)
        route=[start,end]
        label_point=None
        if name=='architecture.png' and source=='ssm' and target=='build':
            route=[(255,745),(255,360),(690,360),(690,280)];label_point=(380,335)
        if name=='artifact-model.png' and source=='run' and target=='evidence':
            route=[(1110,225),(1180,225),(1180,870),(1110,870)];label_point=(1250,710)
        if name=='data-flow.png' and source=='ssm' and target=='build':
            route=[(1100,670),(1770,670),(1770,180),(1740,180)];label_point=(1510,640)
        end=route[-1];start=route[-2]
        d.line(route,fill='#47627D',width=4)
        vx,vy=end[0]-start[0],end[1]-start[1]
        angle=math.atan2(vy,vx)
        points=[end,(end[0]-18*math.cos(angle-.5),end[1]-18*math.sin(angle-.5)),(end[0]-18*math.cos(angle+.5),end[1]-18*math.sin(angle+.5))]
        d.polygon(points,fill='#47627D')
        if label:
            f=ImageFont.truetype(FONT,24);box=d.textbbox((0,0),label,font=f);x=(start[0]+end[0])/2-(box[2]-box[0])/2;y=(start[1]+end[1])/2-18
            if label_point:x=label_point[0]-(box[2]-box[0])/2;y=label_point[1]
            d.rectangle((x-7,y-3,x+box[2]-box[0]+7,y+32),fill='white');d.text((x,y),label,font=f,fill='#304E68')
    for ident,x,y,w,h,text,kind in nodes:
        fill={'process':'#EAF2F8','store':'#ECF5EC','boundary':'#FFF4DF','actor':'#F1F2F4','risk':'#FCECEC'}[kind]
        d.rounded_rectangle((x,y,x+w,y+h),radius=15,fill=fill,outline='#7390AA',width=3)
        lines=text.split('\n'); font=ImageFont.truetype(BOLD,30);line_height=40
        font_size=30
        while max(d.textbbox((0,0),line,font=font)[2] for line in lines)>w-24:
            font_size-=1; font=ImageFont.truetype(BOLD,font_size)
        for i,line in enumerate(lines):
            box=d.textbbox((0,0),line,font=font);d.text((x+(w-(box[2]-box[0]))/2,y+(h-len(lines)*line_height)/2+i*line_height),line,font=font,fill='#172F47')
    image.save(OUT/name)

def main():
    OUT.mkdir(exist_ok=True)
    diagram('architecture.png','AWS DevSecOps architecture',[
      ('git',40,130,300,150,'GitHub main\nReviewed source','actor'),
      ('build',430,130,520,150,'Build job\nTests and security scans','process'),
      ('ecr',1130,130,550,150,'AWS ECR\nImmutable digest and signature','store'),
      ('deploy',430,440,520,160,'Separate deploy job\nVerify trusted key and digest','process'),
      ('ecs',1130,440,550,160,'AWS ECS on EC2\nUID 10001 and read only','process'),
      ('ssm',40,745,430,145,'AWS SSM\nSigning trust and secrets','store'),
      ('falco',1130,745,550,145,'Falco on Linux host\nCloudWatch logs and alarm','boundary'),
      ('local',550,745,420,145,'Local Docker app\n127.0.0.1 port 8080','process')],
      [('git','build','trigger'),('build','ecr','publish'),('ecr','deploy','same run manifest'),('deploy','ecs','verified digest'),('ssm','build','private key'),('ssm','deploy','public key'),('ecs','falco','runtime events')])
    diagram('use-cases.png','Actors and release use cases',[
      ('dev',40,150,350,140,'Developer\nChange reviewed source','actor'),('admin',40,450,350,140,'Account administrator\nConfigure AWS trust','actor'),('review',40,750,350,140,'Evaluator\nInspect evidence','actor'),
      ('release',650,130,590,170,'Publish a verified release\nRun scans build and sign','process'),('verify',650,430,590,170,'Deploy trusted image\nVerify before changing ECS','process'),('observe',650,730,590,170,'Observe health and threats\nLocal AWS and Falco proof','process'),
      ('aws',1420,430,300,170,'AWS services\nScoped roles','actor')],
      [('dev','release','main only'),('admin','verify','configure trust'),('review','observe','read reports'),('release','verify','requires success'),('verify','aws','short lived OIDC'),('verify','observe','health checks')])
    diagram('artifact-model.png','Release and evidence data model',[
      ('source',70,150,440,150,'Source commit\nFull 40 character SHA','store'),('run',650,150,460,150,'Workflow run\nID attempt and jobs','store'),('manifest',1280,150,440,150,'Release manifest\nimage and source','store'),
      ('image',1280,470,440,160,'ECR image digest\nsha256 content identity','store'),('sig',650,470,460,160,'OCI signature artifact\nTrusted key association','store'),('key',70,470,440,160,'SSM public key\nAdministrator trust','store'),
      ('task',1280,800,440,140,'ECS task revision\nDigest and hardening','store'),('evidence',650,800,460,140,'Evidence artifacts\nScans SBOM deployment','store')],
      [('source','run','runs'),('run','manifest','release'),('manifest','image','exact reference'),('image','sig','signature'),('key','sig','key'),('image','task','verified deployment'),('run','evidence','7 day retention')])
    diagram('data-flow.png','Release data flow and trust boundaries',[
      ('source',40,120,360,120,'Developer source\nGitHub repository','actor'),('scan',590,120,550,120,'1 Scan and validate\nNo AWS credentials yet','process'),('build',1340,120,400,120,'2 Assume build role\nBuild scan sign','boundary'),
      ('artifact',1340,340,400,140,'3 Transfer release\nSame workflow artifact','store'),('verify',590,340,550,140,'4 Assume deploy role\nCheck source digest signature','boundary'),('ecs',40,340,360,140,'5 Update ECS\nWait and reject rollback','process'),
      ('logs',40,610,420,120,'Runtime observation\nFalco to CloudWatch','store'),('ssm',680,610,420,120,'SSM signing trust\nPrivate and public scopes','store')],
      [('source','scan','source'),('scan','build','gates pass'),('build','artifact','digest and source'),('artifact','verify','manifest'),('verify','ecs','verified image'),('ecs','logs','events'),('ssm','build','private material'),('ssm','verify','trusted public key')],height=800)
    diagram('attack-tree.png','Attack tree for deploying an untrusted container',[
      ('root',560,100,680,130,'Goal deploy untrusted image\nAlternative attack paths OR','risk'),
      ('source',70,350,490,130,'Compromise main workflow\nAbuse trusted build authority','risk'),('artifact',650,350,490,130,'Tamper with release manifest\nChange digest or source','risk'),('admin',1230,350,490,130,'Bypass normal pipeline\nUse direct admin ECS access','risk'),
      ('guard1',70,600,490,130,'Review source and workflow\nMain only environment rules','boundary'),('guard2',650,600,490,130,'Verify trusted key first\nRepository SHA and digest checks','boundary'),('guard3',1230,600,490,130,'Restrict administrator access\nIndependent audit review','boundary')],
      [('root','source','OR'),('root','artifact','OR'),('root','admin','OR'),('source','guard1','mitigation'),('artifact','guard2','blocked by verifier'),('admin','guard3','residual trust')],height=800)

if __name__=='__main__':main()
