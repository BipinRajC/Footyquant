use crate::api::SupabaseClient;
use crate::models::{FeatureView, MatchPrediction, ModelParams};
use crate::splash_data::{fact_for_index, NextMatch, TeamInfo, WC_FACTS};
use crate::views;
use crossterm::event::{Event, EventStream, KeyCode};
use ratatui::layout::Size;
use ratatui::DefaultTerminal;
use ratatui_image::picker::Picker;
use ratatui_image::protocol::Protocol;
use ratatui_image::Resize;
use std::time::Duration;
use tokio::sync::mpsc;
use tokio_stream::StreamExt;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum View {
    Splash,
    MatchList,
    MatchDetail,
    ModelStats,
}

enum AppMsg {
    Predictions(Vec<MatchPrediction>),
    ModelParams(ModelParams),
    FeatureView(FeatureView),
    Error(String),
    SplashImage(Option<Protocol>, Option<Size>),
    SplashNextMatch(Option<NextMatch>),
    SplashAliveTeams(Vec<TeamInfo>),
}

pub struct App {
    pub view: View,
    pub predictions: Vec<MatchPrediction>,
    pub model_params: Option<ModelParams>,
    pub selected_match: usize,
    pub scroll: usize,
    pub frame_count: usize,
    pub loading: bool,
    pub error: Option<String>,
    pub current_feature: Option<FeatureView>,
    pub should_quit: bool,
    pub splash_image: Option<Protocol>,
    pub splash_image_size: Option<Size>,
    pub next_match: Option<NextMatch>,
    pub alive_teams: Vec<TeamInfo>,
    pub splash_fact_index: usize,
    pub splash_image_loaded: bool,
    pub splash_next_match_loaded: bool,
    pub splash_teams_loaded: bool,
    msg_tx: Option<mpsc::Sender<AppMsg>>,
}

const FRAMES_PER_SECOND: f32 = 30.0;
const FACT_ROTATION_FRAMES: usize = 90;

impl App {
    pub async fn new() -> Result<Self, Box<dyn std::error::Error>> {
        Ok(Self {
            view: View::Splash,
            predictions: Vec::new(),
            model_params: None,
            selected_match: 0,
            scroll: 0,
            frame_count: 0,
            loading: false,
            error: None,
            current_feature: None,
            should_quit: false,
            splash_image: None,
            splash_image_size: None,
            next_match: None,
            alive_teams: Vec::new(),
            splash_fact_index: 0,
            splash_image_loaded: false,
            splash_next_match_loaded: false,
            splash_teams_loaded: false,
            msg_tx: None,
        })
    }

    pub async fn run(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        let terminal = ratatui::init();

        let (msg_tx, msg_rx) = mpsc::channel::<AppMsg>(32);
        self.msg_tx = Some(msg_tx.clone());

        self.spawn_splash_tasks(&terminal, msg_tx);

        let result = self.run_loop(terminal, msg_rx).await;
        ratatui::restore();
        result
    }

    fn spawn_splash_tasks(&self, terminal: &DefaultTerminal, tx: mpsc::Sender<AppMsg>) {
        let term_size = terminal.size().unwrap_or(Size::new(80, 24));

        let picker = match Picker::from_query_stdio() {
            Ok(p) => {
                if std::env::var("TERM_PROGRAM").as_deref() == Ok("vscode") {
                    Picker::halfblocks()
                } else {
                    p
                }
            }
            Err(_) => Picker::halfblocks(),
        };

        let tx_img = tx.clone();
        tokio::task::spawn_blocking(move || {
            let result = encode_splash_image(picker, term_size);
            match result {
                Ok((protocol, size)) => {
                    let _ = tx_img.blocking_send(AppMsg::SplashImage(Some(protocol), Some(size)));
                }
                Err(_) => {
                    let _ = tx_img.blocking_send(AppMsg::SplashImage(None, None));
                }
            }
        });

        let tx_nm = tx.clone();
        tokio::spawn(async move {
            let api = SupabaseClient::new();
            let result = api.fetch_next_match().await;
            let msg = match result {
                Ok(nm) => AppMsg::SplashNextMatch(Some(nm)),
                Err(_) => AppMsg::SplashNextMatch(None),
            };
            let _ = tx_nm.send(msg).await;
        });

        let tx_at = tx.clone();
        tokio::spawn(async move {
            let api = SupabaseClient::new();
            let result = api.fetch_alive_teams().await;
            let teams = result
                .unwrap_or_default()
                .iter()
                .map(|name| TeamInfo::from_name(name))
                .collect();
            let _ = tx_at.send(AppMsg::SplashAliveTeams(teams)).await;
        });
    }

    async fn run_loop(
        &mut self,
        mut terminal: DefaultTerminal,
        mut msg_rx: mpsc::Receiver<AppMsg>,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let period = Duration::from_secs_f32(1.0 / FRAMES_PER_SECOND);
        let mut interval = tokio::time::interval(period);
        let mut events = EventStream::new();

        while !self.should_quit {
            tokio::select! {
                _ = interval.tick() => {
                    self.on_tick();
                    terminal.draw(|frame| views::render(frame, self))?;
                }
                Some(Ok(event)) = events.next() => {
                    self.handle_event(event);
                }
                Some(msg) = msg_rx.recv() => {
                    self.handle_msg(msg);
                }
            }
        }
        Ok(())
    }

    fn on_tick(&mut self) {
        self.frame_count += 1;

        if self.view == View::Splash
            && self.frame_count > 0
            && self.frame_count % FACT_ROTATION_FRAMES == 0
        {
            self.splash_fact_index = (self.splash_fact_index + 1) % WC_FACTS.len();
        }
    }

    fn handle_event(&mut self, event: Event) {
        if let Event::Key(key) = event {
            match key.code {
                KeyCode::Char('q') | KeyCode::Char('Q') => {
                    self.should_quit = true;
                }
                _ if self.view == View::Splash => {
                    self.view = View::MatchList;
                    self.loading = true;
                    self.fetch_data();
                }
                KeyCode::Esc => {
                    if self.view == View::MatchDetail || self.view == View::ModelStats {
                        self.view = View::MatchList;
                        self.scroll = 0;
                    }
                }
                KeyCode::Char('m') | KeyCode::Char('M') => {
                    if self.view != View::Splash {
                        self.view = View::ModelStats;
                        self.scroll = 0;
                    }
                }
                KeyCode::Char('r') | KeyCode::Char('R') => {
                    if self.view != View::Splash {
                        self.loading = true;
                        self.fetch_data();
                    }
                }
                KeyCode::Down => match self.view {
                    View::MatchList => {
                        if !self.predictions.is_empty() {
                            self.selected_match =
                                (self.selected_match + 1).min(self.predictions.len() - 1);
                        }
                    }
                    View::MatchDetail => {
                        self.scroll += 1;
                    }
                    View::ModelStats => {
                        self.scroll += 1;
                    }
                    _ => {}
                },
                KeyCode::Up => match self.view {
                    View::MatchList => {
                        if self.selected_match > 0 {
                            self.selected_match -= 1;
                        }
                    }
                    View::MatchDetail => {
                        if self.scroll > 0 {
                            self.scroll -= 1;
                        }
                    }
                    View::ModelStats => {
                        if self.scroll > 0 {
                            self.scroll -= 1;
                        }
                    }
                    _ => {}
                },
                KeyCode::Enter => {
                    if self.view == View::MatchList && !self.predictions.is_empty() {
                        self.view = View::MatchDetail;
                        self.scroll = 0;
                        self.current_feature = None;
                        self.fetch_feature_for_selected();
                    }
                }
                _ => {}
            }
        }
    }

    fn fetch_data(&self) {
        if let Some(tx) = &self.msg_tx {
            let tx = tx.clone();
            tokio::spawn(async move {
                let api = SupabaseClient::new();
                match api.fetch_predictions().await {
                    Ok(preds) => {
                        let _ = tx.send(AppMsg::Predictions(preds)).await;
                    }
                    Err(e) => {
                        let _ = tx.send(AppMsg::Error(e)).await;
                    }
                }
                match api.fetch_model_params().await {
                    Ok(params) => {
                        let _ = tx.send(AppMsg::ModelParams(params)).await;
                    }
                    Err(e) => {
                        let _ = tx.send(AppMsg::Error(e)).await;
                    }
                }
            });
        }
    }

    fn fetch_feature_for_selected(&self) {
        if let Some(pred) = self.predictions.get(self.selected_match) {
            let match_id = pred.match_id.clone();
            if let Some(tx) = &self.msg_tx {
                let tx = tx.clone();
                tokio::spawn(async move {
                    let api = SupabaseClient::new();
                    match api.fetch_feature_view(&match_id).await {
                        Ok(feature) => {
                            let _ = tx.send(AppMsg::FeatureView(feature)).await;
                        }
                        Err(e) => {
                            let _ = tx.send(AppMsg::Error(e)).await;
                        }
                    }
                });
            }
        }
    }

    fn handle_msg(&mut self, msg: AppMsg) {
        match msg {
            AppMsg::Predictions(preds) => {
                self.predictions = preds;
                self.loading = false;
            }
            AppMsg::ModelParams(params) => {
                self.model_params = Some(params);
            }
            AppMsg::FeatureView(feature) => {
                self.current_feature = Some(feature);
            }
            AppMsg::Error(e) => {
                self.error = Some(e);
                self.loading = false;
            }
            AppMsg::SplashImage(protocol, size) => {
                if let (Some(p), Some(s)) = (protocol, size) {
                    self.splash_image = Some(p);
                    self.splash_image_size = Some(s);
                }
                self.splash_image_loaded = true;
            }
            AppMsg::SplashNextMatch(nm) => {
                self.next_match = nm;
                self.splash_next_match_loaded = true;
            }
            AppMsg::SplashAliveTeams(teams) => {
                self.alive_teams = teams;
                self.splash_teams_loaded = true;
            }
        }
    }

    pub fn current_prediction(&self) -> Option<&MatchPrediction> {
        self.predictions.get(self.selected_match)
    }

    pub fn splash_progress(&self) -> u8 {
        let mut done = 0u8;
        if self.splash_image_loaded {
            done += 1;
        }
        if self.splash_next_match_loaded {
            done += 1;
        }
        if self.splash_teams_loaded {
            done += 1;
        }
        done
    }

    pub fn splash_all_loaded(&self) -> bool {
        self.splash_progress() == 3
    }

    pub fn current_fact(&self) -> &'static str {
        fact_for_index(self.splash_fact_index)
    }
}

fn encode_splash_image(
    picker: Picker,
    term_size: Size,
) -> Result<(Protocol, Size), Box<dyn std::error::Error + Send + Sync>> {
    let dyn_img = image::load_from_memory(include_bytes!("../../data/splash-screen-image.jpg"))?;
    let font_size = picker.font_size();

    let max_cell_w = (term_size.width as f32 * 0.9).max(40.0) as u32;
    let max_cell_h = (term_size.height as f32 * 0.55).max(20.0) as u32;

    let natural_cell_w = dyn_img.width().div_ceil(font_size.width as u32);
    let natural_cell_h = dyn_img.height().div_ceil(font_size.height as u32);

    let scale = (max_cell_w as f32 / natural_cell_w as f32)
        .min(max_cell_h as f32 / natural_cell_h as f32)
        .min(1.0);

    let target_w = (natural_cell_w as f32 * scale) as u16;
    let target_h = (natural_cell_h as f32 * scale) as u16;

    let size = Size::new(target_w, target_h);
    let protocol = picker.new_protocol(dyn_img, size, Resize::Fit(None))?;
    Ok((protocol, size))
}
