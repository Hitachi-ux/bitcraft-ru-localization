#!/usr/bin/env python3
"""Build and install the community translation using the player's own game files."""
import argparse, base64, csv, hashlib, io, json, os, re, shutil, subprocess, sys, tempfile, zlib
from pathlib import Path

BUNDLE = 'remoteassets_assets__6b3aedddc200617548234b0c8142d4e6.bundle'
ORIGINAL_BUNDLE_SHA = '123e86f6c6ddc9b21c081d11a329b42e3fae853372f33793e10c74c37c16af11'
ORIGINAL_CATALOG_SHA = 'ed7c72209e9b23e885f7d57c22ebd3559176f48907289175537232072ad1ff2b'
ROOT = Path(__file__).resolve().parent

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(8*1024*1024),b''): h.update(part)
    return h.hexdigest()

def require_closed():
    if os.name == 'nt':
        p=subprocess.run(['tasklist','/FI','IMAGENAME eq BitCraft.exe','/NH'],capture_output=True,text=True,check=True)
        if 'bitcraft.exe' in p.stdout.lower(): raise RuntimeError('Закройте BitCraft перед установкой или откатом.')
    else:
        raise RuntimeError('Этот установщик поддерживает только Windows.')

def paths(root):
    aa=root/'BitCraft_Data'/'StreamingAssets'/'aa'
    return aa,aa/'StandaloneWindows64'/BUNDLE,aa/'catalog.json',aa/'bitcraft-ru-backup'

def catalog_patch(raw, crc, size):
    obj=json.loads(raw.decode('utf-8-sig')); blob=base64.b64decode(obj['m_ExtraDataString']); needle='6b3aedddc200617548234b0c8142d4e6'.encode('utf-16le')
    if blob.count(needle)!=1: raise RuntimeError('Запись пакета в каталоге не найдена или неоднозначна.')
    start=blob.index(needle);end=blob.find(b'\x07LUnity.ResourceManager',start)
    if end<0: raise RuntimeError('Не найден конец записи пакета.')
    piece=blob[start:end]
    for old,new in [('"m_Crc":1949562651','"m_Crc":'+str(crc).ljust(10)),('"m_BundleSize":1426483502','"m_BundleSize":'+str(size).ljust(10))]:
        a=old.encode('utf-16le');b=new.encode('utf-16le')
        if len(a)!=len(b) or piece.count(a)!=1: raise RuntimeError('Формат записи каталога изменился.')
        piece=piece.replace(a,b,1)
    newblob=blob[:start]+piece+blob[end:];old64=obj['m_ExtraDataString'].encode('ascii');new64=base64.b64encode(newblob)
    if len(new64)!=len(old64) or raw.count(old64)!=1: raise RuntimeError('Невозможно безопасно обновить каталог.')
    result=raw.replace(old64,new64,1);check=json.loads(result.decode('utf-8-sig'))
    if any(obj[k]!=check[k] for k in obj if k!='m_ExtraDataString'): raise RuntimeError('Непредвиденное изменение каталога.')
    return result

def build(bundle, catalog, output_bundle, output_catalog):
    import UnityPy
    from UnityPy.files.BundleFile import BundleFile
    crc_state={'value':0,'calls':0};unpack=BundleFile.decompress_data
    def record(self,*args,**kwargs):
        data=unpack(self,*args,**kwargs)
        if len(args)>=4:
            crc_state['value']=zlib.crc32(data,crc_state['value']);crc_state['calls']+=1
        return data
    edits=json.loads((ROOT/'translations.json').read_text(encoding='utf-8'))['entries']
    mapping={x['index']:x for x in edits}
    if len(mapping)!=len(edits):raise RuntimeError('Повторяющиеся индексы перевода.')
    print('Чтение ресурсов игры...',flush=True);env=UnityPy.load(str(bundle));matched=0;newcsv=None
    for obj in env.objects:
        if obj.type.name!='TextAsset':continue
        item=obj.read()
        if item.m_Name!='ru':continue
        matched+=1;raw=item.m_Script.encode('utf-8','surrogateescape');rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline='')));seen=set()
        for row in rows:
            patch=mapping.get(row['index'])
            if patch:
                if row['source']!=patch['source']:raise RuntimeError('Исходная строка не совпадает: '+row['index'])
                if sorted(re.findall(r'\{\d+[^}]*\}',row['translation']))!=sorted(re.findall(r'\{\d+[^}]*\}',patch['translation'])):raise RuntimeError('Различаются параметры: '+row['index'])
                row['translation']=patch['translation'];seen.add(row['index'])
        if seen!=set(mapping):raise RuntimeError('Часть строк перевода не найдена.')
        buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=['index','source','translation','validated'],lineterminator='\n');writer.writeheader();writer.writerows(rows);newcsv=buffer.getvalue().encode('utf-8');item.m_Script=newcsv.decode('utf-8');item.save()
    if matched!=1:raise RuntimeError('Не удалось однозначно найти русскую локализацию.')
    print('Пересборка игрового пакета; это может занять несколько минут...',flush=True)
    with output_bundle.open('wb') as f:f.write(next(iter(env.files.values())).save('original'))
    del env
    BundleFile.decompress_data=record
    try:
        check=UnityPy.load(str(output_bundle));found=0
        for obj in check.objects:
            if obj.type.name=='TextAsset':
                item=obj.read()
                if item.m_Name=='ru':
                    if item.m_Script.encode('utf-8','surrogateescape')!=newcsv:raise RuntimeError('Повторная проверка перевода не пройдена.')
                    found+=1
        if found!=1 or crc_state['calls']==0:raise RuntimeError('Не удалось проверить собранный пакет.')
    finally:BundleFile.decompress_data=unpack
    output_catalog.write_bytes(catalog_patch(catalog.read_bytes(),crc_state['value'],output_bundle.stat().st_size))
    print('Пакет и контрольная сумма проверены.',flush=True)

def install(root):
    require_closed();aa,bundle,catalog,backup=paths(root)
    if digest(bundle)!=ORIGINAL_BUNDLE_SHA or digest(catalog)!=ORIGINAL_CATALOG_SHA:raise RuntimeError('Версия игровых файлов не совпадает. Игра не изменена.')
    if backup.exists():raise RuntimeError('Резервная папка уже существует. Сначала восстановите оригинал или сохраните её отдельно.')
    stagebundle=bundle.with_name(bundle.name+'.ru-new');stagecatalog=catalog.with_name(catalog.name+'.ru-new')
    if stagebundle.exists() or stagecatalog.exists():raise RuntimeError('Остались временные файлы .ru-new. Проверьте их перед повторной установкой.')
    try:
        build(bundle,catalog,stagebundle,stagecatalog);require_closed()
        if digest(bundle)!=ORIGINAL_BUNDLE_SHA or digest(catalog)!=ORIGINAL_CATALOG_SHA:raise RuntimeError('Игровые файлы изменились во время подготовки.')
        backup.mkdir();shutil.copy2(bundle,backup/'original.bundle');shutil.copy2(catalog,backup/'original-catalog.json')
        if digest(backup/'original.bundle')!=ORIGINAL_BUNDLE_SHA or digest(backup/'original-catalog.json')!=ORIGINAL_CATALOG_SHA:raise RuntimeError('Ошибка проверки резервной копии.')
        info={'bundle':digest(stagebundle),'catalog':digest(stagecatalog)};(backup/'installed.json').write_text(json.dumps(info),encoding='utf-8')
        try:
            os.replace(stagebundle,bundle);os.replace(stagecatalog,catalog)
            if digest(bundle)!=info['bundle'] or digest(catalog)!=info['catalog']:raise RuntimeError('Проверка установленных файлов не прошла.')
        except Exception:
            shutil.copy2(backup/'original.bundle',bundle);shutil.copy2(backup/'original-catalog.json',catalog);raise
        print('Готово. Перевод установлен; оригиналы сохранены в bitcraft-ru-backup.')
    finally:
        for p in (stagebundle,stagecatalog):
            if p.exists():p.unlink()

def restore(root):
    require_closed();aa,bundle,catalog,backup=paths(root);info=json.loads((backup/'installed.json').read_text(encoding='utf-8'))
    if digest(backup/'original.bundle')!=ORIGINAL_BUNDLE_SHA or digest(backup/'original-catalog.json')!=ORIGINAL_CATALOG_SHA:raise RuntimeError('Резервная копия повреждена.')
    if digest(bundle)!=info['bundle'] or digest(catalog)!=info['catalog']:raise RuntimeError('Игровые файлы изменились; откат остановлен, чтобы не перезаписать их.')
    shutil.copy2(backup/'original.bundle',bundle);shutil.copy2(backup/'original-catalog.json',catalog)
    if digest(bundle)!=ORIGINAL_BUNDLE_SHA or digest(catalog)!=ORIGINAL_CATALOG_SHA:raise RuntimeError('Проверка отката не прошла.')
    print('Оригиналы восстановлены. Резервная папка сохранена.')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['install','restore']);parser.add_argument('game',type=Path,nargs='?');args=parser.parse_args()
    game=args.game or Path(input('Путь к папке BitCraft Online: ').strip().strip('"'))
    try:(install if args.action=='install' else restore)(game)
    except Exception as exc:print('Ошибка:',exc,file=sys.stderr);return 1
    return 0
if __name__=='__main__':raise SystemExit(main())