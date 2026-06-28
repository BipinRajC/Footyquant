use crate::api::SupabaseClient;
use crate::models::{FeatureView, MatchPrediction, ModelParams};
use crate::views;
use crossterm::event::{Event, EventStream, KeyCode};
use ratatui::DefaultTerminal;
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
    msg_tx: Option<mpsc::Sender<AppMsg>>,
}

const FRAMES_PER_SECOND: f32 = 30.0;
const SPLASH_DURATION_FRAMES: usize = 180;

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
            msg_tx: None,
        })
    }

    pub async fn run(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        let terminal = ratatui::init();
        let result = self.run_loop(terminal).await;
        ratatui::restore();
        result
    }

    async fn run_loop(
        &mut self,
        mut terminal: DefaultTerminal,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let period = Duration::from_secs_f32(1.0 / FRAMES_PER_SECOND);
        let mut interval = tokio::time::interval(period);
        let mut events = EventStream::new();
        let (msg_tx, mut msg_rx) = mpsc::channel::<AppMsg>(32);

        self.msg_tx = Some(msg_tx.clone());

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

        if self.view == View::Splash && self.frame_count >= SPLASH_DURATION_FRAMES {
            self.view = View::MatchList;
            self.loading = true;
            self.fetch_data();
        }
    }

    fn handle_event(&mut self, event: Event) {
        if let Event::Key(key) = event {
            match key.code {
                KeyCode::Char('q') | KeyCode::Char('Q') => {
                    self.should_quit = true;
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
        }
    }

    pub fn current_prediction(&self) -> Option<&MatchPrediction> {
        self.predictions.get(self.selected_match)
    }
}
