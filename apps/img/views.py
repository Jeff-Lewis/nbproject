# Create your views here.
from django.http import HttpResponse
from django.shortcuts import render_to_response
import  os, sys, logging, string, random
from django.conf import settings
from django.views.static import serve
from django.http import Http404
from base import annotations
from base import utils_response as UR
from base import auth, models as M, signals
from os.path import dirname, abspath


id_log = "".join([ random.choice(string.ascii_letters+string.digits) for i in xrange(0,10)])
logging.basicConfig(level=logging.DEBUG,format='%(asctime)s %(levelname)s %(message)s', filename='/tmp/nb_img_%s.log' % ( id_log,), filemode='a')

def on_file_download(sender, **payload): 
    o = M.FileDownload(user_id=payload["uid"], source_id=payload["id_source"], annotated=payload["annotated"])
    o.save()
    
if settings.MONITOR.get("FILE_DOWNLOAD", False): 
    signals.file_downloaded.connect(on_file_download, weak=False)

def serve_img(req, res, scale, id_source):
    #print "img request of page %s of file %s at res %s and scale %s w/ invite_key=%s and req=%s" % (req.GET["page"], id_file, res, scale, req.GET["invite_key"], req  )
    #TODO: check permissions. 
    uid = UR.getUserId(req);
    if not auth.canReadFile(uid, id_source): 
        return HttpResponse("Error: You don't have credentials to see this file %s " % (id_source,))
    page_str =  settings.IMG_FMT_STRING %  (int(req.GET["page"])-1,)
    filename = req.META["PATH_INFO"].rstrip('/')
    filename = "%s_%s.png" % (filename, page_str)
    response = None
    try: 
        response = serve(req, filename,settings.HTTPD_MEDIA)
        return response
    except Http404: 
        logging.info("missing "+filename)
        basedir = dirname(dirname(dirname(abspath(__file__))))
        #basedir =  sys.modules["servers"].__path__[0].rpartition("/")[0]
        #TODO: would be better to do a redirect to the not_available page
        f = open("%s/content/data/icons/png/not_available.png" % basedir)
        s = f.read()
        f.close()
        return HttpResponse(s)


def serve_doc(req, id_source, annotated=False): 
    serve_dir =  settings.ANNOTATED_DIR if annotated else  settings.REPOSITORY_DIR
    qual = "_annotated" if annotated else  ""
    uid = UR.getUserId(req)
    if not auth.canDownloadPDF(uid, id_source): 
        return HttpResponse("Error: You don't have credentials to see file #%s" % (id_source, ))
    try:   
        response = serve(req, id_source,"%s/%s" % (settings.HTTPD_MEDIA, serve_dir))
        response["Content-Type"]='application/pdf'
        #the following makes sure that: 
        #- the downloaded file name always ends up w/ '.pdf'
        #- it conatains the qualif. '_annotated' if it's... er... well.... annotated : )                
        #- the filename only contains ascii characters, so that we don't get an UnicodeEncodeError since the 
        #  filename is part of the response headers and that HTTP response headers can only contain ascii characters. 
        filename = ""
        try:
            filename = M.Source.objects.get(pk=id_source).title.partition(".pdf")[0].encode("ascii").replace(" ", "_")
        except UnicodeEncodeError: 
            filename = id_source
        filename = "%s%s%s" % (filename, qual, ".pdf")        
        response['Content-Disposition'] = "attachment; filename=%s" % (filename, )
        signals.file_downloaded.send("file", req=req, uid=uid, id_source=id_source, annotated=annotated)
        return response
    except Http404: 
        logging.info("missing "+id_source)
        return HttpResponse("Error - No such file: #%s %s" % (id_source, qual) )

def serve_grades_spreadsheet(req, id_ensemble): 
    uid = UR.getUserId(req)
    if not auth.canSeeGrades(uid, id_ensemble):
        return HttpResponse("Error: You don't have credentials to see grades for class %s" % (id_ensemble,))
    a  = annotations.get_stats_ensemble({"id_ensemble": id_ensemble})    
    files = a["files"]
    stats = a["stats"]
    users = a["users"]
    sections = a["sections"]
    import xlwt
    wbk = xlwt.Workbook()
    s_wd = wbk.add_sheet("word_count")
    s_ch = wbk.add_sheet("char_count")
    s_cm = wbk.add_sheet("comments_count")

    # Default order: file id and user email 
    file_ids = sorted(files)
    user_ids = sorted(users, key=lambda o:users[o]["email"]) 

    row=0
    col=0
    s_wd.write(row, col, "WORDS")
    s_ch.write(row, col, "CHARACTERS")
    s_cm.write(row, col, "COMMENTS")
    col+=1
    s_wd.write(row, col, "SECTION")
    s_ch.write(row, col, "SECTION")
    s_cm.write(row, col, "SECTION")
    col+=1
    val = None
    for f in file_ids: 
        val = files[f]["title"]
        s_wd.write(row, col, val)
        s_ch.write(row, col, val)
        s_cm.write(row, col, val)
        col+=1
    row+=1
    for u in user_ids: 
        col=0
        val = users[u]["email"]
        s_wd.write(row, col, val)
        s_ch.write(row, col, val)
        s_cm.write(row, col, val)
        col+=1
        val = "" if  users[u]["section_id"] is None else  sections[users[u]["section_id"]]["name"] 
        s_wd.write(row, col, val)
        s_ch.write(row, col, val)
        s_cm.write(row, col, val)
        col+=1
        for f in file_ids: 
            stat_id = "%s_%s" % (u,f)
            s_wd.write(row, col, stats[stat_id]["numwords"] if stat_id in stats else "")
            s_ch.write(row, col, stats[stat_id]["numchars"] if stat_id in stats else "")
            s_cm.write(row, col, stats[stat_id]["cnt"] if stat_id in stats else "")
            col+=1
        row+=1
    #now add a sheet for labeled comments if there are any: 
    lcs = M.LabelCategory.objects.filter(ensemble__id=id_ensemble).order_by("id")
    lcs_ids = list(lcs.values_list('id', flat=True))
    cls = M.CommentLabel.objects.select_related("comment", "location").filter(category__in=lcs, grader__id=uid).order_by("comment__location__source__id", "comment__id", "category__id")
    if len(cls)>0:
        s_lc = wbk.add_sheet("labeled_comments")
        #Header row: 
        row=0
        col=0
        s_lc.write(row, col,"SOURCE_ID")
        col+=1
        s_lc.write(row, col,"COMMENT_ID")
        col+=1
        s_lc.write(row, col,"PARENT_ID")
        col+=1
        s_lc.write(row, col,"LOCATION_ID")
        col+=1
        s_lc.write(row, col,"AUTHOR_ID")
        col+=1
        s_lc.write(row, col,"BODY")
        for i in xrange(0,len(lcs)):
            col+=1
            s_lc.write(row, col,"%s - [0:%s]" %(lcs[i].name, lcs[i].pointscale))       
        #Data Rows: 
        previous_comment_id=0
        for j in xrange(0, len(cls)):
            rec = cls[j]
            if previous_comment_id == rec.comment.id:
                #We just need to complete the data that we missed on the previous row. 
                col_grade = col+lcs_ids.index(rec.category_id) #move to the column for the next category for which we have data
                s_lc.write(row, col_grade, rec.grade)
            else: 
                row+=1
                col=0
                s_lc.write(row, col,rec.comment.location.source_id)
                col+=1
                s_lc.write(row, col,rec.comment.id)
                col+=1
                s_lc.write(row, col,rec.comment.parent_id)
                col+=1
                s_lc.write(row, col,rec.comment.location_id)
                col+=1
                s_lc.write(row, col, rec.comment.author_id)
                col+=1
                s_lc.write(row, col, rec.comment.body)
                col+=1
                col_grade = col+lcs_ids.index(rec.category_id) #move to the column for the next category for which we have data
                s_lc.write(row, col_grade, rec.grade) 
            previous_comment_id = rec.comment.id
    import datetime
    a = datetime.datetime.now()
    fn = "stats_%s_%04d%02d%02d_%02d%02d.xls" % (id_ensemble,a.year, a.month, a.day, a.hour, a.minute)
    wbk.save("/tmp/%s" %(fn,))
    response = serve(req, fn,"/tmp/")
    os.remove("/tmp/%s" %(fn,))
    response["Content-Type"]='application/vnd.ms-excel'   
    response['Content-Disposition'] = "attachment; filename=%s" % (fn, )
    return response
