"""Complete player-visible state videos, reconstructed from retained decisions."""
import json
import subprocess
import textwrap
from pathlib import Path
import numpy as np
from .common import ROOT, load_config, read_jsonl, write_csv, write_json

PALETTE = ['#E5D7B1','#E5CC85','#EBC873','#F4E5A2','#84A86A','#617A56','#A9A37B',
           '#D7D9D6','#748A8B','#B9D6DF','#A9D6E5','#3D7D99','#9AC5BE','#D8D8B4']


def frame(state, episode, step, action, stop_reason):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype('DejaVuSans.ttf', 17)
    small = ImageFont.truetype('DejaVuSans.ttf', 14)
    image = Image.new('RGB', (960,720), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((20,12), 'PLAYER-VISIBLE STATE REPLAY (reconstructed; not game screen capture)', fill='black', font=small)
    draw.text((20,38), episode, fill='black',font=font)
    draw.text((20,65), f"Recorded decision {step} | native turn {state.get('turn')} | stop: {stop_reason}", fill='black',font=small)
    cargo=[f'{identity}->{unit.get("transported_by")}' for identity,unit in state.get('own_unit_transport',{}).items() if unit.get('transported')]
    draw.text((20,88),'Carried unit -> ship: '+(', '.join(cargo) or 'none observed'),fill='black',font=small)
    maps = state.get('observation',{}).get('map',{})
    terrain, status = np.asarray(maps.get('terrain',[])), np.asarray(maps.get('status',[]))
    if terrain.ndim==2 and terrain.shape==status.shape:
        from PIL import ImageColor
        rgb = np.zeros((*terrain.T.shape,3),dtype=np.uint8)
        rgb[:] = ImageColor.getrgb('#303846')
        for index,color in enumerate(PALETTE):
            rgb[(terrain.T==index)&(status.T!=0)] = ImageColor.getrgb(color)
        scale = min(900/terrain.shape[0],480/terrain.shape[1])
        width,height = round(terrain.shape[0]*scale),round(terrain.shape[1]*scale)
        x0,y0 = (960-width)//2,110
        image.paste(Image.fromarray(rgb).resize((width,height),Image.Resampling.NEAREST),(x0,y0))
        draw = ImageDraw.Draw(image)
        for kind in ['city','unit']:
            groups={}
            for identity,obj in state.get('observation',{}).get(kind,{}).items():
                if obj.get('x') is None or obj.get('y') is None: continue
                groups.setdefault((obj['x'],obj['y']),[]).append(str(identity))
            for (tile_x,tile_y),identities in groups.items():
                x,y = x0+(tile_x+.5)*scale,y0+(tile_y+.5)*scale
                box=(x-5,y-5,x+5,y+5)
                if kind=='city': draw.rectangle(box,fill='#0072B2',outline='white',width=2)
                else: draw.ellipse(box,fill='#D55E00',outline='white',width=2)
                draw.text((x+6,y-16 if kind=='city' else y+2),('C:' if kind=='city' else 'U:')+','.join(identities),font=small,fill='white',stroke_width=1,stroke_fill='black')
    else:
        draw.text((160,300),'No map supplied in this SDK state',fill='black',font=font)
    metrics=state.get('task_metrics',{})
    draw.text((20,610),f"score={metrics.get('mini_score')} | goal={metrics.get('mini_goal')} | native game={metrics.get('status')} | player={metrics.get('success',metrics.get('is_mini_success'))}",fill='black',font=small)
    for i,line in enumerate(textwrap.wrap(str(action),110)[:2]):
        draw.text((20,640+i*20),line,fill='black',font=small)
    draw.text((20,692),'Dark: undiscovered | Orange circles: units | Blue squares: cities | 1 frame per recorded decision',fill='black',font=small)
    return image


def build_videos(config):
    import imageio_ffmpeg
    run=ROOT/'runs'/config['run_id']
    index=[]
    for result in sorted((run/'episodes').glob('*/attempt*/result.json')):
        row=json.loads(result.read_text())
        if not row.get('ended_at') or row['stop_reason'] in {'running','interrupted','infrastructure_error'}: continue
        folder=result.parent
        initial=json.loads((folder/'initial.json').read_text())
        steps=read_jsonl(folder/'steps.jsonl')
        video=folder/'player_visible_replay.mp4'
        if not video.exists():
            command=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo',
                     '-pix_fmt','rgb24','-s','960x720','-r','1','-i','-','-an','-c:v','libx264','-preset','fast',
                     '-crf','24','-pix_fmt','yuv420p','-movflags','+faststart',str(video)]
            with subprocess.Popen(command,stdin=subprocess.PIPE) as process:
                state=initial
                process.stdin.write(frame(state,row['episode_id'],'INITIAL','INITIAL STATE',row['stop_reason']).tobytes())
                for step in steps:
                    state=step.get('after',step.get('before',state))
                    action=step.get('native_action','NO ACTION SUBMITTED')
                    if 'native_action' in step and action is None: action='END_TURN'
                    process.stdin.write(frame(state,row['episode_id'],step['decision_id'].rsplit('-decision',1)[-1],action,row['stop_reason']).tobytes())
                process.stdin.close()
                if process.wait()!=0:
                    video.unlink(missing_ok=True)
                    raise RuntimeError(f'Video encoding failed: {row["attempt_id"]}')
            write_json(folder/'replay_metadata.json',{'type':'reconstructed_player_visible_state','source':'initial.json + steps.jsonl',
                                                     'frames':len(steps)+1,'fps':1,'video_path':str(video)})
        index.append({'episode_id':row['episode_id'],'attempt_id':row['attempt_id'],'video_path':str(video),
                      'video_type':'reconstructed_player_visible_state','frames':len(steps)+1,'fps':1,
                      'source_steps':str(folder/'steps.jsonl')})
    output=ROOT/'reports/development'
    output.mkdir(parents=True,exist_ok=True)
    write_csv(output/'video_index.csv',index,['episode_id','attempt_id','video_path','video_type','frames','fps','source_steps'])
    return index


if __name__=='__main__':
    print('Videos retained on server:',len(build_videos(load_config())))
