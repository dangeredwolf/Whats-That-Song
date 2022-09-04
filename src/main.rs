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
}

#[derive(Deserialize)]
struct ShazamResponse {
    timestamp: u32,
    track: ShazamTrack,
}

struct Handler;

lazy_static! {
    static ref RE: Regex = Regex::new(
            r"(?i)https?://((fx|px|vx)?twitter|twxtter|twittpr)\.com/\w{1,15}/status(es)?/\d+"
        ).unwrap();
    static ref CLIENT: reqwest::Client = reqwest::Client::new();
}

#[async_trait]
impl EventHandler for Handler {
    async fn message(&self, _ctx: Context, msg: serenity::model::channel::Message) {
        // If message is empty and it's in a guild, then return
        if msg.content.is_empty() && msg.guild_id.is_some() {
            return;
        }

        if msg.author.bot { return; } // Ignore pings from bots
        println!("CREATE_MESSAGE from {}", msg.author.name);
        if !msg.attachments.is_empty() {
            println!("Attachments: {:?}", msg.attachments);
            // Iterate through attachments and find the first one with a content_type that contains "video"
            for attachment in msg.attachments {
                let content_type = attachment.content_type.unwrap();
                if content_type.contains("video") || content_type.contains("audio") {
                    println!("Found media attachment: {}", attachment.url);

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