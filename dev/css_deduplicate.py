import re
import sys
from collections import OrderedDict

def parse_css_blocks(css_content):
    # Split content into blocks while preserving media queries
    blocks = []
    current_block = ""
    brace_count = 0
    in_media_query = False
    media_query_content = ""
    
    for line in css_content.splitlines():
        stripped_line = line.strip()
        
        # Handle media query
        if '@media' in line:
            in_media_query = True
            media_query_content = line + '\n'
            brace_count = line.count('{') - line.count('}')
            continue
            
        if in_media_query:
            media_query_content += line + '\n'
            brace_count += line.count('{') - line.count('}')
            
            if brace_count == 0:
                blocks.append(media_query_content)
                in_media_query = False
                media_query_content = ""
            continue
            
        # Regular CSS rules
        if stripped_line.startswith('}'):
            if current_block:
                blocks.append(current_block + line + '\n')
                current_block = ""
            continue
            
        if stripped_line.endswith('{'):
            if current_block:
                blocks.append(current_block)
            current_block = line + '\n'
        elif current_block or stripped_line:
            current_block += line + '\n'
    
    if current_block:
        blocks.append(current_block)
    
    return blocks

def extract_selector(block):
    # Extract selector from CSS block
    match = re.match(r'^([^{]+){', block.strip())
    return match.group(1).strip() if match else None

def clean_css(input_file, output_file):
    # Read the CSS file
    with open(input_file, 'r', encoding='utf-8') as f:
        css_content = f.read()
    
    # Store root variables separately (they should be at the top)
    root_vars = ""
    root_match = re.search(r':root\s*{[^}]+}', css_content)
    if root_match:
        root_vars = root_match.group(0) + '\n\n'
    
    # Parse into blocks
    blocks = parse_css_blocks(css_content)
    
    # Keep track of unique selectors, maintaining order
    unique_blocks = OrderedDict()
    media_queries = []
    
    for block in blocks:
        if '@media' in block:
            media_queries.append(block)
            continue
            
        selector = extract_selector(block)
        if selector:
            unique_blocks[selector] = block

    # Write the cleaned CSS
    with open(output_file, 'w', encoding='utf-8') as f:
        # Write root variables first
        if root_vars:
            f.write(root_vars)
        
        # Write regular CSS rules
        f.write('/* Regular CSS Rules */\n')
        for block in unique_blocks.values():
            f.write(block + '\n')
        
        # Write media queries last
        if media_queries:
            f.write('\n/* Media Queries */\n')
            for query in media_queries:
                f.write('\n' + query + '\n')

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python css_deduplicate.py input.css output.css")
        sys.exit(1)
        
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    clean_css(input_file, output_file)
    print(f"CSS cleaned and written to {output_file}")