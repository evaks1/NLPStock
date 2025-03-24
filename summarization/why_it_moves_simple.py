from typing import Dict, List, Literal
from datetime import datetime, timezone
import logging
import time
import json
from pathlib import Path

# Import from other modules using direct imports
from ..data_fetchers.article_extractor import extract_article_text
from ..nlp_processing.nlp_processor import process_articles_batch
from ..utils.file_operations import ensure_directory, load_json, save_json
from .summarize import summarize_article, summarize_articles

logger = logging.getLogger(__name__)

def get_news_articles(symbol: str):
    """Get news articles for the specified stock from local JSON files."""
    news_path = Path(f"STOCK_DB/news/{symbol}_news.json")
    if not news_path.exists():
        logger.warning(f"No news file found for {symbol}")
        return []
    
    try:
        articles = load_json(news_path)
        # Take the 5 most recent articles
        return articles[:5] if len(articles) > 5 else articles
    except Exception as e:
        logger.error(f"Error loading news for {symbol}: {e}")
        return []

def process_company_data(symbol: str, exchange: str, news_articles: List[Dict], classification: Literal["gainer", "loser"]):
    """Process the company data and news articles to generate a summary based on classification."""
    direction = "up" if classification == "gainer" else "down" if classification == "loser" else "neutral"
    logger.info(f"Processing data for symbol: {symbol} - Classified as {classification}")

    if not news_articles:
        logger.info(f"No news articles found for {symbol}")
        return {
            "symbol": symbol,
            "exchange": exchange,
            "type": classification,
            "period": "day",
            "summary": f"There are no news currently affecting the stock price, fluctuations might be due to market conditions.",
        }

    # Count articles with text and extract text for those without it
    articles_with_text = 0
    for article in news_articles:
        # Check if article already has text
        if "full_article_text" in article and article["full_article_text"] and article["full_article_text"] != "Full article text not found.":
            articles_with_text += 1
            continue
            
        # If not, try to extract it
        url = article.get("url", article.get("link", ""))
        if url:
            full_article_text = extract_article_text(url)
            article["full_article_text"] = full_article_text
            if full_article_text != "Full article text not found.":
                articles_with_text += 1

    # Skip summary if all articles have no text
    if articles_with_text == 0:
        logger.info(f"All articles for {symbol} returned 'Full article text not found' - skipping summary")
        return {
            "symbol": symbol,
            "exchange": exchange,
            "type": classification,
            "period": "day",
            "summary": f"There are no news currently affecting the stock price, fluctuations might be due to market conditions.",
        }
    else:
        try:
            # Process articles with NLP to extract key information
            processed_articles = process_articles_batch(news_articles, symbol, symbol)
            
            # Print the processed text after NLP
            print("\n" + "="*80)
            print(f"PROCESSED TEXT AFTER NLP FOR {symbol}:")
            print("="*80)
            
            summaries = []
            for i, article in enumerate(processed_articles):
                # Print the condensed text
                condensed_text = article.get('condensed_text', '')
                if condensed_text:
                    print(f"\nArticle {i+1}:")
                    print("-" * 40)
                    print(condensed_text)
                    print("-" * 40)
                    
                    # Generate summary
                    summary = summarize_article(condensed_text, symbol, direction)
                    if summary:
                        summaries.append(summary)
                    time.sleep(2)  # 2-second delay between summary requests

            summaries = [s for s in summaries if s]
            if not summaries:
                logger.info(f"No valid summaries generated for {symbol}")
                return {
                    "symbol": symbol,
                    "exchange": exchange,
                    "type": classification,
                    "period": "day",
                    "summary": "No valid article summaries could be generated.",
                }
                
            explanation = summarize_articles(summaries, symbol)
            return {"symbol": symbol, "exchange": exchange, "type": classification, "summary": explanation}
        except Exception as e:
            logger.error(f"Error summarizing articles for {symbol}: {e}")
            return {
                "symbol": symbol,
                "exchange": exchange,
                "type": classification,
                "period": "day",
                "summary": "There was an error generating the summary.",
            }

def classify_company(net_change_percentage: float):
    """Classify the company based on net change percentage."""
    if net_change_percentage > 0:
        return "gainer"
    else:
        return "loser"

def why_it_moves(symbol: str, exchange: str, daily_change_percentage: float):
    """Generate a summary of why a stock is moving and save it locally."""
    classification = classify_company(daily_change_percentage)

    news_articles = get_news_articles(symbol)
    summary = {
        **process_company_data(symbol, exchange, news_articles, classification),
        "daily_change_percentage": daily_change_percentage,
        "date_generated": datetime.now(timezone.utc).isoformat(),
    }

    # Save the summary to a local file
    output_dir = ensure_directory("STOCK_DB/movers")
    output_file = Path(output_dir) / f"{symbol}_summary.json"
    save_json(summary, output_file)

    logger.info(f"{exchange}/{symbol} mover summary saved to {output_file}")
    return summary

def process_all_stocks():
    """Process all stocks that have news data and generate summaries."""
    news_dir = Path("STOCK_DB/news")
    if not news_dir.exists():
        logger.error("News directory not found")
        return
    
    # Get all news files
    news_files = list(news_dir.glob("*_news.json"))
    logger.info(f"Found {len(news_files)} stocks with news data")
    
    for news_file in news_files:
        try:
            # Extract symbol from filename (remove _news.json)
            symbol = news_file.stem.replace("_news", "")
            
            # Default to NASDAQ exchange if not known
            exchange = "NASDAQ"
            
            # Use a random change percentage for demonstration
            # In a real scenario, you would get this from price data
            import random
            daily_change = random.uniform(-5.0, 5.0)
            
            logger.info(f"Processing {symbol} with change {daily_change:.2f}%")
            summary = why_it_moves(symbol, exchange, daily_change)
            
            # Print a brief version of the summary
            print(f"\n{symbol} ({exchange}) - Change: {daily_change:.2f}%")
            print(f"Classification: {summary['type']}")
            print(f"Summary: {summary['summary'][:200]}...\n")
            
            # Add a small delay to avoid rate limiting
            time.sleep(3)
            
        except Exception as e:
            logger.error(f"Error processing {news_file.name}: {e}") 