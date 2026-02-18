import os, sys, threading
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import filedialog, messagebox
sys.path.insert(0, os.path.dirname(__file__))
from analyzer import analyze_clip
from timeline import auto_cut_timeline, sync_to_beats, timeline_stats, format_timeline_for_display
from exporter import render_video, export_fcpxml, export_edl, export_csv, export_transcript

BG_DARK="#1a1a2e"; BG_MID="#16213e"; BG_CARD="#0f3460"
C_ACCENT="#e94560"; C_GREEN="#00b894"; C_YELLOW="#fdcb6e"; C_GRAY="#636e72"
F_BIG=("Segoe UI",20,"bold"); F_MED=("Segoe UI",12); F_SM=("Segoe UI",10); F_MONO=("Consolas",10)

class WeddingCutApp:
    def __init__(self):
        self.root=tk.Tk(); self.root.title("WeddingCut Pro v1.0")
        self.root.geometry("1200x800"); self.root.minsize(900,600); self.root.configure(bg=BG_DARK)
        self.video_files=[]; self.analyses=[]; self.timeline_segments=[]
        self.opt_remove_silences=tk.BooleanVar(value=True); self.opt_remove_fillers=tk.BooleanVar(value=True)
        self.opt_scene_det=tk.BooleanVar(value=True); self.opt_transcribe=tk.BooleanVar(value=True)
        self.opt_language=tk.StringVar(value="it"); self.opt_model=tk.StringVar(value="base")
        self.opt_sil_db=tk.DoubleVar(value=-40.0); self.opt_sil_min=tk.DoubleVar(value=0.5)
        self.opt_framerate=tk.StringVar(value="25"); self.opt_music_file=tk.StringVar(value="")
        self.opt_sync_beats=tk.BooleanVar(value=False)
        self._build_ui()
        self._log("Benvenuto in WeddingCut Pro!")
        self._log("1) Aggiungi video  2) Analizza  3) Auto-Cut  4) Esporta")

    def _build_ui(self):
        self.root.rowconfigure(1,weight=1); self.root.columnconfigure(0,weight=1)
        self._build_header()
        main=tk.Frame(self.root,bg=BG_DARK); main.grid(row=1,column=0,sticky="nsew",padx=8,pady=4)
        main.rowconfigure(0,weight=1); main.columnconfigure(0,minsize=260); main.columnconfigure(1,weight=1); main.columnconfigure(2,minsize=250)
        self._build_files(main); self._build_center(main); self._build_settings(main); self._build_footer()

    def _build_header(self):
        h=tk.Frame(self.root,bg=BG_CARD,height=56); h.grid(row=0,column=0,sticky="ew"); h.grid_propagate(False)
        tk.Label(h,text="  WeddingCut Pro",font=F_BIG,bg=BG_CARD,fg="white").pack(side="left",pady=8)
        bf=tk.Frame(h,bg=BG_CARD); bf.pack(side="right",padx=10)
        for txt,cmd,col in [("+ Aggiungi Video",self._add_videos,C_GREEN),("Analizza",self._start_analysis,"#0984e3"),("Auto-Cut",self._generate_timeline,"#6c5ce7"),("Esporta",self._open_export,"#00cec9")]:
            self._btn(bf,txt,cmd,col).pack(side="left",padx=3,pady=8)

    def _build_files(self,parent):
        f=tk.Frame(parent,bg=BG_MID); f.grid(row=0,column=0,sticky="nsew",padx=(0,5))
        f.rowconfigure(1,weight=1); f.columnconfigure(0,weight=1)
        tk.Label(f,text="VIDEO CARICATI",font=("Segoe UI",9,"bold"),bg=BG_MID,fg=C_GRAY).grid(row=0,column=0,sticky="w",padx=10,pady=6)
        lf=tk.Frame(f,bg=BG_MID); lf.grid(row=1,column=0,sticky="nsew",padx=8)
        lf.rowconfigure(0,weight=1); lf.columnconfigure(0,weight=1)
        self.lb=tk.Listbox(lf,bg="#0d1b2a",fg="white",selectbackground=C_ACCENT,font=F_SM,borderwidth=0,highlightthickness=1,highlightbackground=BG_CARD,activestyle="none",selectmode=tk.EXTENDED)
        sb=tk.Scrollbar(lf,command=self.lb.yview); self.lb.configure(yscrollcommand=sb.set)
        self.lb.grid(row=0,column=0,sticky="nsew"); sb.grid(row=0,column=1,sticky="ns")
        tk.Label(f,text="Usa 'Aggiungi Video' per caricare i tuoi file",font=("Segoe UI",8),bg=BG_MID,fg=C_GRAY,justify="center").grid(row=2,column=0,pady=4)
        br=tk.Frame(f,bg=BG_MID); br.grid(row=3,column=0,pady=6,padx=8,sticky="ew")
        self._btn(br,"Rimuovi",self._remove_sel,C_GRAY,small=True).pack(side="left",padx=2)
        self._btn(br,"Pulisci",self._clear_all,C_GRAY,small=True).pack(side="left",padx=2)

    def _build_center(self,parent):
        f=tk.Frame(parent,bg=BG_DARK); f.grid(row=0,column=1,sticky="nsew",padx=4)
        f.rowconfigure(0,weight=2); f.rowconfigure(1,weight=1); f.columnconfigure(0,weight=1)
        tf=tk.Frame(f,bg=BG_MID); tf.grid(row=0,column=0,sticky="nsew",pady=(0,4))
        tf.rowconfigure(1,weight=1); tf.columnconfigure(0,weight=1)
        hr=tk.Frame(tf,bg=BG_MID); hr.grid(row=0,column=0,sticky="ew",padx=10,pady=5)
        tk.Label(hr,text="TIMELINE GENERATA",font=("Segoe UI",9,"bold"),bg=BG_MID,fg=C_GRAY).pack(side="left")
        self.tl_stats=tk.Label(hr,text="",font=F_SM,bg=BG_MID,fg=C_GREEN); self.tl_stats.pack(side="right")
        cols=("N","File","Da","A","Durata","Tipo","Score")
        self.tree=ttk.Treeview(tf,columns=cols,show="headings",selectmode="browse")
        style=ttk.Style(); style.theme_use("clam")
        style.configure("Treeview",background="#0d1b2a",foreground="white",fieldbackground="#0d1b2a",font=F_SM,rowheight=22)
        style.configure("Treeview.Heading",background=BG_CARD,foreground="white",font=("Segoe UI",9,"bold"))
        style.map("Treeview",background=[("selected",C_ACCENT)])
        for c,w in [("N",36),("File",180),("Da",68),("A",68),("Durata",68),("Tipo",80),("Score",55)]:
            self.tree.heading(c,text=c); self.tree.column(c,width=w,anchor="center")
        tsb=tk.Scrollbar(tf,orient="vertical",command=self.tree.yview); tsb.grid(row=1,column=1,sticky="ns")
        self.tree.configure(yscrollcommand=tsb.set); self.tree.grid(row=1,column=0,sticky="nsew",padx=(8,0),pady=(0,8))
        self.tree.tag_configure("speech",foreground="#dfe6e9"); self.tree.tag_configure("silence",foreground=C_GRAY)
        self.tree.tag_configure("filler",foreground=C_YELLOW); self.tree.tag_configure("best_scene",foreground=C_GREEN)
        lf=tk.Frame(f,bg=BG_MID); lf.grid(row=1,column=0,sticky="nsew")
        lf.rowconfigure(1,weight=1); lf.columnconfigure(0,weight=1)
        tk.Label(lf,text="LOG",font=("Segoe UI",9,"bold"),bg=BG_MID,fg=C_GRAY).grid(row=0,column=0,sticky="w",padx=10,pady=4)
        self.log_widget=tk.Text(lf,bg="#0d1b2a",fg="#b2bec3",font=F_MONO,borderwidth=0,highlightthickness=0,state="disabled",wrap="word")
        lsb=tk.Scrollbar(lf,command=self.log_widget.yview); lsb.grid(row=1,column=1,sticky="ns",pady=(0,8))
        self.log_widget.configure(yscrollcommand=lsb.set); self.log_widget.grid(row=1,column=0,sticky="nsew",padx=(8,0),pady=(0,8))

    def _build_settings(self,parent):
        outer=tk.Frame(parent,bg=BG_MID); outer.grid(row=0,column=2,sticky="nsew",padx=(5,0))
        outer.rowconfigure(1,weight=1); outer.columnconfigure(0,weight=1)
        tk.Label(outer,text="IMPOSTAZIONI",font=("Segoe UI",9,"bold"),bg=BG_MID,fg=C_GRAY).grid(row=0,column=0,sticky="w",padx=12,pady=(10,2))
        canvas=tk.Canvas(outer,bg=BG_MID,highlightthickness=0); vsb=tk.Scrollbar(outer,orient="vertical",command=canvas.yview)
        sf=tk.Frame(canvas,bg=BG_MID); sf.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0),window=sf,anchor="nw"); canvas.configure(yscrollcommand=vsb.set)
        vsb.grid(row=1,column=1,sticky="ns"); canvas.grid(row=1,column=0,sticky="nsew")
        canvas.bind("<MouseWheel>",lambda e:canvas.yview_scroll(-1 if e.delta>0 else 1,"units"))
        self._sec(sf,"TAGLIO AUTOMATICO"); self._chk(sf,"Rimuovi silenzi",self.opt_remove_silences)
        self._chk(sf,"Rimuovi filler (ehm, tipo...)",self.opt_remove_fillers); self._chk(sf,"Rileva scene migliori",self.opt_scene_det)
        self._lbl(sf,"Soglia silenzio (dB):"); self._slider(sf,self.opt_sil_db,-60,-20,1)
        self._lbl(sf,"Silenzio minimo (sec):"); self._slider(sf,self.opt_sil_min,0.1,3.0,0.1)
        self._sec(sf,"TRASCRIZIONE WHISPER AI"); self._chk(sf,"Trascrivi audio (locale, gratuito)",self.opt_transcribe)
        self._lbl(sf,"Lingua:"); lr=tk.Frame(sf,bg=BG_MID); lr.pack(fill="x",padx=12,pady=2)
        for code,lab in [("it","IT"),("en","EN"),("fr","FR"),("es","ES")]:
            tk.Radiobutton(lr,text=lab,variable=self.opt_language,value=code,bg=BG_MID,fg="white",selectcolor=BG_CARD,activebackground=BG_MID,font=F_SM).pack(side="left",padx=3)
        self._lbl(sf,"Modello:"); mr=tk.Frame(sf,bg=BG_MID); mr.pack(fill="x",padx=12,pady=2)
        for m,d in [("tiny","Rapido"),("base","Medio"),("small","Preciso")]:
            tk.Radiobutton(mr,text=f"{m}\n({d})",variable=self.opt_model,value=m,bg=BG_MID,fg="white",selectcolor=BG_CARD,activebackground=BG_MID,font=("Segoe UI",8),justify="center").pack(side="left",padx=4)
        self._sec(sf,"MUSICA E BEAT"); self._chk(sf,"Sincronizza tagli ai beat",self.opt_sync_beats)
        self._lbl(sf,"File musica (opzionale):");  mrow=tk.Frame(sf,bg=BG_MID); mrow.pack(fill="x",padx=12,pady=2)
        tk.Entry(mrow,textvariable=self.opt_music_file,bg="#0d1b2a",fg="white",font=F_SM,insertbackground="white",borderwidth=0).pack(side="left",fill="x",expand=True)
        self._btn(mrow,"...",self._pick_music,C_GRAY,small=True).pack(side="right")
        self._sec(sf,"ESPORTAZIONE"); self._lbl(sf,"Frame rate:"); frr=tk.Frame(sf,bg=BG_MID); frr.pack(fill="x",padx=12,pady=2)
        for fr in ["24","25","30"]:
            tk.Radiobutton(frr,text=f"{fr}fps",variable=self.opt_framerate,value=fr,bg=BG_MID,fg="white",selectcolor=BG_CARD,activebackground=BG_MID,font=F_SM).pack(side="left",padx=3)

    def _build_footer(self):
        ft=tk.Frame(self.root,bg=BG_MID,height=34); ft.grid(row=2,column=0,sticky="ew"); ft.grid_propagate(False); ft.columnconfigure(1,weight=1)
        self.status_lbl=tk.Label(ft,text="Pronto",font=F_SM,bg=BG_MID,fg="white"); self.status_lbl.grid(row=0,column=0,padx=12,pady=5)
        self.pbar=ttk.Progressbar(ft,orient="horizontal",mode="determinate",length=400); self.pbar.grid(row=0,column=1,padx=12,pady=6,sticky="ew")
        self.plabel=tk.Label(ft,text="",font=F_SM,bg=BG_MID,fg=C_GRAY); self.plabel.grid(row=0,column=2,padx=12)

    def _btn(self,parent,text,cmd,color=BG_CARD,small=False):
        font=("Segoe UI",9) if small else ("Segoe UI",10,"bold"); px,py=(6,2) if small else (12,5)
        b=tk.Button(parent,text=text,command=cmd,bg=color,fg="white",font=font,relief="flat",cursor="hand2",activebackground=color,activeforeground="white",padx=px,pady=py,bd=0)
        b.bind("<Enter>",lambda e:b.config(bg=self._lt(color))); b.bind("<Leave>",lambda e:b.config(bg=color)); return b

    def _lt(self,c):
        try:
            h=c.lstrip("#"); r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
            return f"#{min(255,r+25):02x}{min(255,g+25):02x}{min(255,b+25):02x}"
        except: return c

    def _chk(self,p,text,var):
        tk.Checkbutton(p,text=text,variable=var,bg=BG_MID,fg="white",selectcolor=BG_CARD,activebackground=BG_MID,activeforeground="white",font=F_SM,anchor="w").pack(fill="x",padx=12,pady=2)

    def _lbl(self,p,text):
        tk.Label(p,text=text,bg=BG_MID,fg=C_GRAY,font=F_SM,anchor="w").pack(fill="x",padx=12,pady=(5,0))

    def _sec(self,p,text):
        tk.Label(p,text=text,bg=BG_MID,fg=C_ACCENT,font=("Segoe UI",9,"bold"),anchor="w").pack(fill="x",padx=12,pady=(12,3))

    def _slider(self,p,var,lo,hi,res):
        row=tk.Frame(p,bg=BG_MID); row.pack(fill="x",padx=12,pady=2)
        tk.Label(row,textvariable=var,bg=BG_MID,fg=C_GREEN,font=F_SM,width=5).pack(side="right")
        tk.Scale(row,variable=var,from_=lo,to=hi,resolution=res,orient="horizontal",bg=BG_MID,fg="white",troughcolor=BG_CARD,highlightthickness=0,sliderlength=12,showvalue=False,length=140).pack(side="left",fill="x",expand=True)

    def _add_videos(self):
        files=filedialog.askopenfilenames(title="Seleziona video",filetypes=[("Video","*.mp4 *.mov *.avi *.mkv *.mts *.m2ts *.wmv *.webm"),("Tutti","*.*")])
        if not files: return
        added=0
        for p in files:
            if p not in self.video_files and os.path.isfile(p):
                self.video_files.append(p); self.lb.insert("end",os.path.basename(p)); added+=1
        self._log(f"Aggiunti {added} file. Totale: {len(self.video_files)}")

    def _remove_sel(self):
        sel=list(self.lb.curselection())
        for i in reversed(sel): self.lb.delete(i); self.video_files.pop(i)
        self._log(f"Rimossi {len(sel)} file")

    def _clear_all(self):
        self.video_files.clear(); self.lb.delete(0,"end"); self.analyses.clear(); self.timeline_segments.clear()
        for row in self.tree.get_children(): self.tree.delete(row)
        self.tl_stats.config(text=""); self._log("Lista svuotata")

    def _pick_music(self):
        p=filedialog.askopenfilename(title="Seleziona musica",filetypes=[("Audio","*.mp3 *.wav *.aac *.flac *.m4a"),("Tutti","*.*")])
        if p: self.opt_music_file.set(p); self._log(f"Musica: {os.path.basename(p)}")

    def _start_analysis(self):
        if not self.video_files: messagebox.showwarning("Attenzione","Aggiungi almeno un video!"); return
        self.analyses.clear(); threading.Thread(target=self._analysis_worker,daemon=True).start()

    def _analysis_worker(self):
        opts={"silence_threshold_db":self.opt_sil_db.get(),"min_silence_duration":self.opt_sil_min.get(),"run_transcription":self.opt_transcribe.get(),"transcription_language":self.opt_language.get(),"whisper_model":self.opt_model.get(),"run_scene_detection":self.opt_scene_det.get(),"run_beat_detection":self.opt_sync_beats.get(),"audio_file_for_beats":self.opt_music_file.get() or None}
        total=len(self.video_files); self._set_status("Analisi in corso..."); self._log(f"\nInizio analisi di {total} file...")
        for i,path in enumerate(self.video_files):
            self._prog(int(i/total*100),f"Analizzo {os.path.basename(path)}..."); self._log(f"\n[{i+1}/{total}] {os.path.basename(path)}")
            try:
                result=analyze_clip(path,opts); self.analyses.append(result)
                self._log(f"  OK: {len(result.get('silences',[]))} silenzi, {len(result.get('filler_segments',[]))} filler, {len(result.get('best_scenes',[]))} scene top")
                for err in result.get("errors",[]): self._log(f"  ATTENZIONE: {err}")
            except Exception as e: self._log(f"  ERRORE: {e}")
        self._prog(100,"Analisi completata!"); self._set_status("Analisi completata"); self._log("\nFatto! Ora clicca 'Auto-Cut'.")

    def _generate_timeline(self):
        if not self.analyses: messagebox.showwarning("Attenzione","Prima esegui 'Analizza'!"); return
        self._log("\nGenerazione timeline automatica...")
        opts={"remove_silences":self.opt_remove_silences.get(),"remove_fillers":self.opt_remove_fillers.get(),"min_segment_duration":0.3,"padding_seconds":0.05}
        try:
            segs=auto_cut_timeline(self.analyses,opts)
            if self.opt_sync_beats.get():
                beats=[b for a in self.analyses for b in a.get("beat_times",[])]
                if beats: segs=sync_to_beats(segs,beats); self._log("  Tagli sincronizzati ai beat")
            self.timeline_segments=segs
            for row in self.tree.get_children(): self.tree.delete(row)
            for item in format_timeline_for_display(segs):
                self.tree.insert("","end",values=(item["index"],item["source_file"][:22],f"{item['source_start']:.1f}s",f"{item['source_end']:.1f}s",f"{item['duration']:.1f}s",item["type"],f"{item['score']:.0f}" if item["score"]>0 else "-"),tags=(item["type"],))
            st=timeline_stats(segs); dur=st["total_duration"]; mm,ss=int(dur//60),dur%60
            self._log(f"Timeline: {st['n_segments']} segmenti, {mm}:{ss:05.2f}")
            self.tl_stats.config(text=f"{st['n_segments']} segmenti  |  {mm}:{ss:05.2f}")
        except Exception as e: self._log(f"ERRORE: {e}")

    def _open_export(self):
        if not self.timeline_segments: messagebox.showwarning("Attenzione","Prima genera la timeline con 'Auto-Cut'!"); return
        dlg=tk.Toplevel(self.root); dlg.title("Esporta"); dlg.geometry("480x340"); dlg.configure(bg=BG_MID); dlg.grab_set()
        tk.Label(dlg,text="Scegli il formato di esportazione",font=F_MED,bg=BG_MID,fg="white").pack(pady=14)
        var=tk.StringVar(value="video")
        for val,lab,desc in [("video","Video finale (.mp4)","Rendering completo pronto da consegnare"),("fcpxml","DaVinci Resolve XML (.fcpxml)","Apri in DaVinci Resolve (gratuito)"),("edl","EDL universale (.edl)","Compatibile con Premiere, Avid, Final Cut"),("csv","Foglio Excel (.csv)","Lista leggibile di tutti i tagli"),("transcript","Trascrizione testo (.txt)","Testo completo del parlato")]:
            row=tk.Frame(dlg,bg=BG_MID); row.pack(fill="x",padx=20,pady=2)
            tk.Radiobutton(row,text=lab,variable=var,value=val,bg=BG_MID,fg="white",selectcolor=BG_CARD,activebackground=BG_MID,font=F_SM).pack(side="left")
            tk.Label(row,text=f"  {desc}",bg=BG_MID,fg=C_GRAY,font=("Segoe UI",8)).pack(side="left")
        def go():
            fmt=var.get(); dlg.destroy(); self._run_export(fmt)
        self._btn(dlg,"Esporta",go,C_ACCENT).pack(pady=14)

    def _run_export(self,fmt):
        ext={"video":[("MP4","*.mp4")],"fcpxml":[("FCPXML","*.fcpxml")],"edl":[("EDL","*.edl")],"csv":[("CSV","*.csv")],"transcript":[("Testo","*.txt")]}
        default={"video":"wedding_finale.mp4","fcpxml":"wedding_timeline.fcpxml","edl":"wedding_timeline.edl","csv":"wedding_tagli.csv","transcript":"trascrizione.txt"}
        out=filedialog.asksaveasfilename(title="Salva come...",filetypes=ext[fmt],initialfile=default[fmt])
        if not out: return
        threading.Thread(target=self._export_worker,args=(fmt,out),daemon=True).start()

    def _export_worker(self,fmt,out):
        self._set_status(f"Esportazione {fmt}..."); self._log(f"\nEsporto {fmt}: {os.path.basename(out)}")
        try:
            fr=int(self.opt_framerate.get())
            if fmt=="video": render_video(self.timeline_segments,out,progress_callback=lambda p,m:self._prog(p,m))
            elif fmt=="fcpxml": export_fcpxml(self.timeline_segments,out,frame_rate=str(fr))
            elif fmt=="edl": export_edl(self.timeline_segments,out,frame_rate=fr)
            elif fmt=="csv": export_csv(self.timeline_segments,out)
            elif fmt=="transcript": export_transcript(self.analyses,out)
            self._log(f"  Salvato: {out}"); self._set_status("Esportazione completata!"); self._prog(100,"Fatto!")
            self.root.after(0,lambda:messagebox.showinfo("Successo!",f"File salvato:\n{out}"))
        except Exception as e:
            self._log(f"  ERRORE: {e}"); self._set_status("Errore")
            self.root.after(0,lambda:messagebox.showerror("Errore",str(e)))

    def _log(self,msg):
        def _do():
            self.log_widget.configure(state="normal"); self.log_widget.insert("end",msg+"\n")
            self.log_widget.see("end"); self.log_widget.configure(state="disabled")
        self.root.after(0,_do)

    def _set_status(self,text): self.root.after(0,lambda:self.status_lbl.config(text=text))

    def _prog(self,val,msg=""):
        self.root.after(0,lambda:(self.pbar.configure(value=val),self.plabel.config(text=msg)))

    def run(self): self.root.mainloop()

if __name__=="__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    WeddingCutApp().run()
