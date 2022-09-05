use std::env;
use std::time::Duration;
use lazy_static::lazy_static;
use regex::Regex;

use dotenv;
use serde::Deserialize;

use serenity::async_trait;
use serenity::model::gateway::Ready;
use serenity::prelude::*;
use tokio::time::sleep;

extern crate reqwest;

#[derive(Deserialize)]
struct ShazamMetadata {
    text: String,
    title: String
}

#[derive(Deserialize)]
struct ShazamSection {
    metadata: Option<Vec<ShazamMetadata>>
}

#[derive(Deserialize)]
struct ShazamProvider {
    #[serde(rename = "type")]
    provider_type: String
}

#[derive(Deserialize)]
struct ShazamHub {
    providers: Vec<ShazamProvider>
}

#[derive(Deserialize)]
struct ShazamImages {
    background: String,
    coverart: String,
    coverarthq: String
}

#[derive(Deserialize)]
struct ShazamTrack {
    title: String,
    subtitle: String,
    url: String,
    images: ShazamImages,
    sections: Vec<ShazamSection>
}

#[derive(Deserialize)]
struct ShazamResponse {
    timestamp: Option<u64>,
    track: Option<ShazamTrack>,
}

struct Handler;

lazy_static! {
    static ref RE: Regex = Regex::new(
            r"(?i)https?://((fx|px|vx)?twitter|twxtter|twittpr)\.com/\w{1,15}/status(es)?/\d+"
        ).unwrap();
    static ref CLIENT: reqwest::Client = reqwest::Client::new();
}

async fn fetch_Url(url: &str) -> ShazamResponse {
    let api_server = dotenv::var("API_SERVER").unwrap();
    let url = format!("{}{}", api_server, url);
    let data = match CLIENT.get(url).send().await {
        Ok(data) => data.json::<ShazamResponse>().await.unwrap(),
        Err(err) => {
            panic!("API request failed: {:?}", err);
        }
    };
    return data;
}

async fn fetch_direct(url: &str) -> ShazamResponse {
    let url = format!("/direct?url={}", url);
    return fetch_Url(&url).await;
}

async fn fetch_twitter(url: &str) -> ShazamResponse {
    let id = url.split('/').last().unwrap();
    let url = &format!("/twitter/{}", id);
    return fetch_Url(&url).await;
}

async fn fetch_ytdl(url: &str) -> ShazamResponse {
    let url = format!("/ytdl?url={}", url);
    return fetch_Url(&url).await;
}

async fn handle_response(ctx: Context, msg: &serenity::model::channel::Message, data: ShazamResponse) {
    let track = match data.track {
        Some(track) => track,
        None => {
            println!("No track found");
            return;
        }
    };
    let title = track.title;
    let subtitle = track.subtitle;
    let url = track.url;
    let coverart = track.images.coverart;
    let mut message = format!("**{}** by **{}**", title, subtitle);
    if url != "" {
        message = format!("{}

{}", message, url);
    }
    if coverart != "" {
        message = format!("{} {}", message, coverart);
    }
    if let Err(why) = msg.channel_id.say(&ctx.http, message).await {
        println!("Error sending message: {:?}", why);
    }
}

#[async_trait]
impl EventHandler for Handler {
    async fn message(&self, ctx: Context, msg: serenity::model::channel::Message) {
        // If message is empty and it's in a guild, then return
        if msg.content.is_empty() && msg.guild_id.is_some() {
            return;
        }

        if msg.author.bot { return; } // Ignore pings from bots
        println!("CREATE_MESSAGE from {}", msg.author.name);
        if !msg.attachments.is_empty() {
            println!("Attachments: {:?}", &msg.attachments);
            // Iterate through attachments and find the first one with a content_type that contains "video"
            for attachment in &msg.attachments {
                let content_type = attachment.content_type.as_ref().unwrap();
                if content_type.contains("video") || content_type.contains("audio") {
                    println!("Found media attachment: {}", attachment.url);
                    // Try fetching using direct media
                    let data = fetch_direct(&attachment.url).await;
                    if data.track.is_some() {
                        handle_response(ctx, &msg, data).await;
                    }

                    println!("Fetched from API!");
                    break;
                }
            }
        }
    }

    async fn ready(&self, _: Context, ready: Ready) {
        if let Some(shard) = ready.shard {
            // Note that array index 0 is 0-indexed, while index 1 is 1-indexed.
            //
            // This may seem unintuitive, but it models Discord's behaviour.
            println!("READY ({}) on shard {}/{}!", ready.user.name, shard[0], shard[1],);
        }
    }
}

#[tokio::main]
async fn main() {
    
    dotenv::dotenv().expect("Failed to load .env file!");
    let token = env::var("DISCORD_TOKEN").expect("Expected a token in the environment");

    let intents = GatewayIntents::GUILD_MESSAGES | GatewayIntents::DIRECT_MESSAGES;
    let mut client =
        Client::builder(&token, intents).event_handler(Handler).await.expect("Err creating client");

    let manager = client.shard_manager.clone();

    tokio::spawn(async move {
        loop {
            sleep(Duration::from_secs(30)).await;

            let lock = manager.lock().await;
            let shard_runners = lock.runners.lock().await;

            for (id, runner) in shard_runners.iter() {
                println!(
                    "Shard ID {} is {} with a latency of {:?}",
                    id, runner.stage, runner.latency,
                );
            }
        }
    });

    if let Err(why) = client.start_shards(1).await {
        println!("Client error: {:?}", why);
    }
}