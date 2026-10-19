"""SIMULATION ONLY: rasterize this repository's axis-aligned warehouse boxes."""
import argparse
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

def make_map(world,output):
    source=Path(world).read_bytes()
    root=ET.fromstring(source)
    width,height,res,ox,oy=240,160,.05,-6.,-4.
    boxes=[]
    for model in root.findall("./world/model"):
        assert model.findtext("static")=="true"
        pose=list(map(float,model.findtext("pose","0 0 0 0 0 0").split()))
        assert pose[3:]==[0,0,0],"Fixture generator only supports axis-aligned models"
        for link in model.findall("link"):
            assert link.find("pose") is None
            for collision in link.findall("collision"):
                assert collision.find("pose") is None
                size=list(map(float,collision.findtext("geometry/box/size").split()))
                if pose[2]+size[2]/2<=.01:continue
                boxes.append((pose[0],pose[1],size[0]/2,size[1]/2))
    pixels=bytearray()
    for row in reversed(range(height)):
        for col in range(width):
            x,y=ox+(col+.5)*res,oy+(row+.5)*res
            occupied=any(abs(x-bx)<=hx+res/2 and abs(y-by)<=hy+res/2 for bx,by,hx,hy in boxes)
            pixels.append(0 if occupied else 254)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.with_suffix(".pgm").write_bytes(f"P5\n# SIMULATION warehouse.sdf geometry, NOT a LiDAR survey\n{width} {height}\n255\n".encode()+pixels)
    output.with_suffix(".yaml").write_text(f"image: {output.name}.pgm\nresolution: {res}\norigin: [{ox}, {oy}, 0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n")
    print("SIMULATION fixture:",output,"SDF sha256:",hashlib.sha256(source).hexdigest())

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--world",default=str(Path(__file__).resolve().parents[1]/"worlds/warehouse.sdf"))
    parser.add_argument("--output",required=True)
    args=parser.parse_args();make_map(args.world,args.output)
