import argparse
import logging
import sys

from jra_scraper.services.race_scraping_service import RaceScrapingService


def setup_logging(level: int = logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def interactive_mode():
    service = RaceScrapingService()
    print("競馬レース情報取得システム")
    print("=" * 50)
    print("終了するには 'q' または 'quit' と入力")
    print()

    while True:
        try:
            race_name = input("レース名を入力してください: ").strip()
            if not race_name:
                continue
            if race_name.lower() in ("q", "quit"):
                print("終了します")
                break

            print(f"\n「{race_name}」を検索中...")
            dfs = service.run(race_name)

            if not dfs:
                race_id = input("レースIDを入力してください（検索結果なし）: ").strip()
                if race_id:
                    dfs = service.run_by_id(race_id)

            if dfs:
                service.display_summary()
                save = input("\nCSVに保存しますか？ (y/n): ").strip().lower()
                if save == "y":
                    paths = service.save_csv()
                    print("保存完了:")
                    for key, path in paths.items():
                        print(f"  {key}: {path}")
            else:
                print("データを取得できませんでした")

        except KeyboardInterrupt:
            print("\n終了します")
            break
        except Exception as e:
            logging.exception("Error: %s", e)
            print(f"エラーが発生しました: {e}")

    service.close()


def single_run(race_name: str, output_dir: str, save_csv: bool = True, save_excel: bool = False):
    service = RaceScrapingService()
    dfs = service.run(race_name)
    if dfs:
        service.display_summary()
        if save_csv:
            paths = service.save_csv(output_dir=output_dir)
            for key, path in paths.items():
                print(f"  CSV保存: {path}")
        if save_excel:
            path = service.save_excel(output_dir=output_dir)
            print(f"  Excel保存: {path}")
    else:
        print("データを取得できませんでした")
    service.close()


def main():
    parser = argparse.ArgumentParser(
        description="競馬レース情報取得システム - netkeibaからレース情報を取得",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python -m jra_scraper.cli.main "日本ダービー"
  python -m jra_scraper.cli.main "有馬記念" --output ./data --excel
  python -m jra_scraper.cli.main --interactive
        """,
    )
    parser.add_argument("race_name", nargs="?", help="レース名（例: 日本ダービー、有馬記念）")
    parser.add_argument("--output", "-o", default="output", help="出力ディレクトリ（デフォルト: output）")
    parser.add_argument("--excel", "-e", action="store_true", help="Excel形式でも保存")
    parser.add_argument("--interactive", "-i", action="store_true", help="対話モードで起動")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログを出力")
    args = parser.parse_args()

    setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    if args.interactive:
        interactive_mode()
    elif args.race_name:
        single_run(args.race_name, args.output, save_csv=True, save_excel=args.excel)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
