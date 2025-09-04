from PIL import Image, ImageDraw, ImageFont
import io
from typing import Dict, Optional, Tuple
from app.core.config import settings
import os
import logging

logger = logging.getLogger(__name__)

class TemplateComposer:
    def __init__(self):
        self.templates = {
            'instagram_story': {
                'size': (1080, 1920),
                'before_position': (90, 400),  # x, y
                'after_position': (90, 1100),
                'before_size': (900, 450),     # width, height
                'after_size': (900, 450),
                'template_file': 'story_template.png'
            },
            'instagram_post': {
                'size': (1080, 1080),
                'before_position': (40, 200),
                'after_position': (580, 200),
                'before_size': (500, 400),
                'after_size': (500, 400),
                'template_file': 'post_template.png'
            },
            'social_wide': {
                'size': (1200, 630),
                'before_position': (50, 150),
                'after_position': (650, 150),
                'before_size': (500, 330),
                'after_size': (500, 330),
                'template_file': 'wide_template.png'
            }
        }
    
    def create_composite(self, 
                        before_chart_bytes: bytes, 
                        after_chart_bytes: bytes,
                        token_symbol: str,
                        profit_percentage: float,
                        template_type: str = 'instagram_post') -> Optional[bytes]:
        """Create composite image with before/after charts on template"""
        
        try:
            template_config = self.templates.get(template_type)
            if not template_config:
                logger.error(f"Unknown template type: {template_type}")
                return None
            
            # Load template
            template_path = os.path.join('assets', template_config['template_file'])
            if os.path.exists(template_path):
                template = Image.open(template_path)
            else:
                # Create simple template if file doesn't exist
                template = self._create_simple_template(template_config, token_symbol, profit_percentage)
            
            # Load and resize charts
            before_chart = Image.open(io.BytesIO(before_chart_bytes))
            after_chart = Image.open(io.BytesIO(after_chart_bytes))
            
            before_chart = before_chart.resize(template_config['before_size'], Image.LANCZOS)
            after_chart = after_chart.resize(template_config['after_size'], Image.LANCZOS)
            
            # Paste charts on template
            template.paste(before_chart, template_config['before_position'])
            template.paste(after_chart, template_config['after_position'])
            
            # Save to bytes
            output = io.BytesIO()
            template.save(output, format='PNG', quality=95)
            output.seek(0)
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error creating composite: {e}")
            return None
    
    def _create_simple_template(self, config: Dict, token_symbol: str, profit_percentage: float) -> Image.Image:
        """Create a simple template if custom template doesn't exist"""
        template = Image.new('RGB', config['size'], color='#1a1a1a')
        draw = ImageDraw.Draw(template)
        
        # Add text (you can customize this)
        try:
            # Use default font if custom font not available
            title_font = ImageFont.load_default()
            
            # Title
            title = f"${token_symbol} Performance"
            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_width = title_bbox[2] - title_bbox[0]
            draw.text(((config['size'][0] - title_width) // 2, 50), title, fill='white', font=title_font)
            
            # Profit percentage
            profit_text = f"+{profit_percentage:.1f}% Profit"
            profit_bbox = draw.textbbox((0, 0), profit_text, font=title_font)
            profit_width = profit_bbox[2] - profit_bbox[0]
            draw.text(((config['size'][0] - profit_width) // 2, 100), profit_text, fill='#00ff88', font=title_font)
            
        except:
            pass  # Skip text if font issues
        
        return template

template_composer = TemplateComposer()
