"""
Gradio GUI for Makefile commands
크롤러 프로젝트의 Makefile 명령어들을 GUI로 실행할 수 있는 웹 인터페이스
"""
import gradio as gr
import subprocess
import os
import threading
import queue
import time
from pathlib import Path
from typing import Optional, Generator


# 전역 변수로 실행 중인 프로세스 관리
running_processes = {}
process_lock = threading.Lock()


def read_category_file(filepath: str) -> list[str]:
    """
    카테고리 파일을 읽어서 리스트로 반환

    Args:
        filepath: 카테고리 파일 경로

    Returns:
        카테고리 이름 리스트
    """
    categories = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 주석이나 빈 줄 제외
                if line and not line.startswith('#'):
                    categories.append(line)
    except FileNotFoundError:
        pass
    return categories


def save_category_file(filepath: str, categories: list[str]):
    """
    선택된 카테고리를 파일로 저장

    Args:
        filepath: 저장할 파일 경로
        categories: 카테고리 이름 리스트
    """
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("# Oliveyoung 카테고리 필터링\n")
        f.write("# '#'으로 시작하는 줄은 주석으로 처리됩니다\n\n")
        for category in categories:
            f.write(f"{category}\n")


def run_command_streaming(cmd: list[str], task_id: str) -> Generator[str, None, None]:
    """
    셸 명령어를 실행하고 실시간으로 출력을 스트리밍

    Args:
        cmd: 실행할 명령어 리스트
        task_id: 작업 ID (프로세스 추적용)

    Yields:
        실시간 출력 문자열
    """
    output_queue = queue.Queue()

    def enqueue_output(pipe, output_queue):
        try:
            for line in iter(pipe.readline, b''):
                if line:
                    output_queue.put(('out', line))
            pipe.close()
        except Exception as e:
            output_queue.put(('err', str(e)))

    try:
        # unbuffered 모드로 실행
        env = os.environ.copy()
        env['PYTHONUNBUFFERED'] = '1'

        # 프로세스 그룹 생성 (자식 프로세스도 함께 종료하기 위해)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,  # unbuffered
            cwd=os.getcwd(),
            env=env,
            start_new_session=True  # 새로운 프로세스 그룹 생성
        )

        # 프로세스 등록
        with process_lock:
            running_processes[task_id] = process

        # 출력 읽기 쓰레드 시작
        thread = threading.Thread(target=enqueue_output, args=(process.stdout, output_queue))
        thread.daemon = True
        thread.start()

        output_lines = []
        last_yield_time = time.time()

        while True:
            # 프로세스 종료 확인
            poll_result = process.poll()

            # 큐에서 출력 읽기 (논블로킹)
            try:
                msg_type, line = output_queue.get(timeout=0.05)
                if msg_type == 'out':
                    # 바이트를 문자열로 변환 (에러 무시)
                    try:
                        decoded_line = line.decode('utf-8')
                    except UnicodeDecodeError:
                        try:
                            decoded_line = line.decode('cp949')  # Windows Korean
                        except:
                            decoded_line = line.decode('utf-8', errors='ignore')
                    output_lines.append(decoded_line)
                elif msg_type == 'err':
                    output_lines.append(f"Error: {line}\n")
            except queue.Empty:
                pass

            # 0.5초마다 또는 새 출력이 있을 때 업데이트
            current_time = time.time()
            if current_time - last_yield_time >= 0.5:
                if output_lines:
                    yield ''.join(output_lines)
                last_yield_time = current_time

            # 프로세스 종료 처리
            if poll_result is not None:
                # 남은 출력 모두 읽기
                time.sleep(0.1)  # 마지막 출력 대기
                while not output_queue.empty():
                    try:
                        msg_type, line = output_queue.get_nowait()
                        if msg_type == 'out':
                            try:
                                decoded_line = line.decode('utf-8')
                            except UnicodeDecodeError:
                                try:
                                    decoded_line = line.decode('cp949')
                                except:
                                    decoded_line = line.decode('utf-8', errors='ignore')
                            output_lines.append(decoded_line)
                    except queue.Empty:
                        break
                break

        # 최종 출력
        final_output = ''.join(output_lines)

        if process.returncode != 0:
            final_output += f"\n\n❌ 프로세스가 오류와 함께 종료되었습니다 (exit code: {process.returncode})"
        else:
            final_output += "\n\n✅ 완료!"

        yield final_output

    except Exception as e:
        yield f"❌ Error: {str(e)}"
    finally:
        # 프로세스 등록 해제
        with process_lock:
            if task_id in running_processes:
                del running_processes[task_id]


def stop_process(task_id_prefix: str):
    """
    실행 중인 프로세스를 중지

    Args:
        task_id_prefix: 중지할 작업 ID 접두사

    Returns:
        중지 결과 메시지
    """
    with process_lock:
        # task_id_prefix로 시작하는 프로세스 찾기
        matching_tasks = [tid for tid in running_processes.keys() if tid.startswith(task_id_prefix)]

        if matching_tasks:
            for task_id in matching_tasks:
                process = running_processes[task_id]

                # 프로세스 그룹 전체 종료 (자식 프로세스 포함)
                import signal
                try:
                    # SIGTERM으로 정상 종료 시도
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # 강제 종료
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    # 이미 종료된 프로세스
                    pass
                except Exception as e:
                    # fallback: 일반 terminate/kill
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()

            return f"✅ 작업 중지됨 (자식 프로세스 포함)"
        else:
            return f"⚠️ 실행 중인 작업을 찾을 수 없습니다"


def install_dependencies():
    """의존성 설치"""
    task_id = "install"
    for output in run_command_streaming(["make", "install"], task_id):
        yield output


def oliveyoung_crawl(max_items: int, output_filename: str, save_to_db: bool, selected_categories: list):
    """Oliveyoung 크롤링 실행"""
    import shutil

    # 원본 category_filter.txt 백업
    backup_file = ".category_filter_backup.txt"
    if os.path.exists("category_filter.txt"):
        shutil.copy("category_filter.txt", backup_file)

    try:
        # 체크 안 된 카테고리 = 제외할 카테고리
        # 전체 카테고리에서 선택된 것을 빼면 제외할 카테고리
        excluded_categories = [cat for cat in all_categories if cat not in selected_categories]

        if excluded_categories:
            save_category_file("category_filter.txt", excluded_categories)
            yield f"📋 {len(selected_categories)}개 카테고리를 크롤링합니다 ({len(excluded_categories)}개 제외).\n\n"
        else:
            # 모든 카테고리 선택됨 (빈 필터)
            save_category_file("category_filter.txt", [])
            yield f"📋 모든 카테고리를 크롤링합니다.\n\n"

        env_vars = {
            "MAX_ITEMS": str(max_items),
            "OUTPUT_FILENAME": output_filename if output_filename else "oliveyoung_products_0812.xlsx",
        }

        if save_to_db:
            env_vars["USE_DB"] = "true"

        cmd = ["make", "oliveyoung-crawl"] + [f"{k}={v}" for k, v in env_vars.items()]

        task_id = f"oliveyoung_crawl_{int(time.time())}"
        for output in run_command_streaming(cmd, task_id):
            yield output

    finally:
        # 원본 category_filter.txt 복원
        if os.path.exists(backup_file):
            shutil.copy(backup_file, "category_filter.txt")
            os.remove(backup_file)


def oliveyoung_crawl_new(existing_excel: str, max_items: int, output_filename: str, save_to_db: bool, selected_categories: list):
    """Oliveyoung 최신 상품 크롤링"""
    import shutil

    # 원본 category_filter.txt 백업
    backup_file = ".category_filter_backup.txt"
    if os.path.exists("category_filter.txt"):
        shutil.copy("category_filter.txt", backup_file)

    try:
        # 체크 안 된 카테고리 = 제외할 카테고리
        # 전체 카테고리에서 선택된 것을 빼면 제외할 카테고리
        excluded_categories = [cat for cat in all_categories if cat not in selected_categories]

        if excluded_categories:
            save_category_file("category_filter.txt", excluded_categories)
            yield f"📋 {len(selected_categories)}개 카테고리를 크롤링합니다 ({len(excluded_categories)}개 제외).\n\n"
        else:
            # 모든 카테고리 선택됨 (빈 필터)
            save_category_file("category_filter.txt", [])
            yield f"📋 모든 카테고리를 크롤링합니다.\n\n"

        env_vars = {
            "EXISTING_EXCEL": existing_excel if existing_excel else "data/oliveyoung_20250929.xlsx",
            "MAX_ITEMS": str(max_items),
            "OUTPUT_FILENAME": output_filename if output_filename else "oliveyoung_new_products.xlsx",
        }

        if save_to_db:
            env_vars["USE_DB"] = "true"

        cmd = ["make", "oliveyoung-crawl-new"] + [f"{k}={v}" for k, v in env_vars.items()]

        task_id = f"oliveyoung_crawl_new_{int(time.time())}"
        for output in run_command_streaming(cmd, task_id):
            yield output

    finally:
        # 원본 category_filter.txt 복원
        if os.path.exists(backup_file):
            shutil.copy(backup_file, "category_filter.txt")
            os.remove(backup_file)


def oliveyoung_upload(from_db: bool, input_file: str, save_to_db: bool):
    """Oliveyoung 업로드 변환"""
    env_vars = {}

    if from_db:
        env_vars["FROM_DB"] = "true"
    elif input_file:
        env_vars["INPUT_FILE"] = input_file
    else:
        yield "**Error:** Excel 파일 경로를 입력하거나 'DB에서 로딩' 체크박스를 선택하세요."
        return

    if save_to_db:
        env_vars["USE_DB"] = "true"

    cmd = ["make", "oliveyoung-upload"] + [f"{k}={v}" for k, v in env_vars.items()]

    task_id = f"oliveyoung_upload_{int(time.time())}"
    for output in run_command_streaming(cmd, task_id):
        yield output


def asmama_crawl(list_url: str):
    """Asmama 크롤링"""
    env_vars = {
        "LIST_URL": list_url if list_url else "http://www.asmama.com/shop/bestseller.html?xcode=REVIEW"
    }

    cmd = ["make", "asmama-crawl"] + [f"{k}={v}" for k, v in env_vars.items()]

    task_id = f"asmama_crawl_{int(time.time())}"
    for output in run_command_streaming(cmd, task_id):
        yield output


def validate_celeb():
    """셀럽 정보 필수 검증"""
    task_id = f"validate_celeb_{int(time.time())}"
    for output in run_command_streaming(["make", "validate-celeb"], task_id):
        yield output


def upload_celeb():
    """셀럽 검증된 데이터 업로드 변환"""
    task_id = f"upload_celeb_{int(time.time())}"
    for output in run_command_streaming(["make", "upload-celeb"], task_id):
        yield output


# 전체 카테고리 목록 로드
all_categories = read_category_file("all_categories.txt")
excluded_categories = read_category_file("category_filter.txt")

# 기본값: 전체 - 제외 목록 = 포함할 카테고리 (체크된 상태)
default_categories = [cat for cat in all_categories if cat not in excluded_categories]


# Gradio UI 구성
with gr.Blocks(title="크롤러 컨트롤 패널", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🕷️ 크롤러 컨트롤 패널")
    gr.Markdown("Makefile 명령어를 GUI로 실행할 수 있습니다.")

    with gr.Tabs():
        # 설치 탭
        with gr.Tab("⚙️ 설치"):
            gr.Markdown("### 의존성 설치")
            gr.Markdown("Python 패키지와 Playwright 브라우저를 설치합니다.")
            with gr.Row():
                install_btn = gr.Button("의존성 설치", variant="primary", scale=4)
                install_stop_btn = gr.Button("중지", variant="stop", scale=1)
            install_output = gr.Textbox(label="실행 결과", lines=15, max_lines=30, autoscroll=True)

            install_btn.click(
                install_dependencies,
                outputs=install_output,
                show_progress="full"
            )
            install_stop_btn.click(
                lambda: stop_process("install"),
                outputs=install_output
            )

        # Oliveyoung 크롤링 탭
        with gr.Tab("🛍️ Oliveyoung 크롤링"):
            gr.Markdown("### 카테고리 필터 설정")
            gr.Markdown("크롤링할 카테고리를 선택하세요. (기본값: category_filter.txt)")

            category_selector = gr.CheckboxGroup(
                choices=all_categories,
                value=default_categories,
                label="크롤링할 카테고리 선택",
                info="✅ 체크된 카테고리만 크롤링됩니다 (체크 안 된 것은 제외)"
            )

            gr.Markdown("---")
            gr.Markdown("### 전체 카테고리 크롤링")
            with gr.Row():
                oy_max_items = gr.Number(label="카테고리당 최대 아이템 수", value=1, precision=0)
                oy_output_filename = gr.Textbox(label="출력 파일명", value="oliveyoung_products_0812.xlsx")
            oy_save_db = gr.Checkbox(label="PostgreSQL에도 저장", value=False)
            with gr.Row():
                oy_crawl_btn = gr.Button("크롤링 시작", variant="primary", scale=4)
                oy_stop_btn = gr.Button("중지", variant="stop", scale=1)
            oy_crawl_output = gr.Textbox(label="실행 결과", lines=15, max_lines=30, autoscroll=True)

            oy_crawl_btn.click(
                oliveyoung_crawl,
                inputs=[oy_max_items, oy_output_filename, oy_save_db, category_selector],
                outputs=oy_crawl_output,
                show_progress="full"
            )
            oy_stop_btn.click(
                lambda: stop_process("oliveyoung_crawl"),
                outputs=oy_crawl_output
            )

            gr.Markdown("---")
            gr.Markdown("### 최신 상품만 크롤링")
            with gr.Row():
                oy_existing_excel = gr.Textbox(label="기존 Excel 파일 경로", value="data/oliveyoung_20250929.xlsx")
                oy_new_max_items = gr.Number(label="카테고리당 최대 아이템 수", value=15, precision=0)
            with gr.Row():
                oy_new_output_filename = gr.Textbox(label="출력 파일명", value="oliveyoung_new_products.xlsx")
                oy_new_save_db = gr.Checkbox(label="PostgreSQL에도 저장", value=False)
            with gr.Row():
                oy_new_crawl_btn = gr.Button("최신 상품 크롤링 시작", variant="primary", scale=4)
                oy_new_stop_btn = gr.Button("중지", variant="stop", scale=1)
            oy_new_crawl_output = gr.Textbox(label="실행 결과", lines=15, max_lines=30, autoscroll=True)

            oy_new_crawl_btn.click(
                oliveyoung_crawl_new,
                inputs=[oy_existing_excel, oy_new_max_items, oy_new_output_filename, oy_new_save_db, category_selector],
                outputs=oy_new_crawl_output,
                show_progress="full"
            )
            oy_new_stop_btn.click(
                lambda: stop_process("oliveyoung_crawl_new"),
                outputs=oy_new_crawl_output
            )

        # Oliveyoung 업로드 탭
        with gr.Tab("📤 Oliveyoung 업로드 변환"):
            gr.Markdown("### Qoo10 업로드 형식으로 변환")
            oy_from_db = gr.Checkbox(label="PostgreSQL에서 로딩", value=False)
            oy_input_file = gr.Textbox(label="Excel 파일 경로 (DB에서 로딩하지 않는 경우)", placeholder="data/oliveyoung_products.xlsx")
            oy_upload_save_db = gr.Checkbox(label="PostgreSQL에도 저장", value=False)
            with gr.Row():
                oy_upload_btn = gr.Button("업로드 변환 시작", variant="primary", scale=4)
                oy_upload_stop_btn = gr.Button("중지", variant="stop", scale=1)
            oy_upload_output = gr.Textbox(label="실행 결과", lines=15, max_lines=30, autoscroll=True)

            oy_upload_btn.click(
                oliveyoung_upload,
                inputs=[oy_from_db, oy_input_file, oy_upload_save_db],
                outputs=oy_upload_output,
                show_progress="full"
            )
            oy_upload_stop_btn.click(
                lambda: stop_process("oliveyoung_upload"),
                outputs=oy_upload_output
            )

        # Asmama 크롤링 탭
        with gr.Tab("🏪 Asmama 크롤링"):
            gr.Markdown("### 베스트셀러 페이지 크롤링")
            asmama_url = gr.Textbox(
                label="리스트 페이지 URL",
                value="http://www.asmama.com/shop/bestseller.html?xcode=REVIEW",
                placeholder="http://www.asmama.com/shop/bestseller.html?xcode=REVIEW"
            )
            with gr.Row():
                asmama_crawl_btn = gr.Button("크롤링 시작", variant="primary", scale=4)
                asmama_stop_btn = gr.Button("중지", variant="stop", scale=1)
            asmama_crawl_output = gr.Textbox(label="실행 결과", lines=15, max_lines=30, autoscroll=True)

            asmama_crawl_btn.click(
                asmama_crawl,
                inputs=asmama_url,
                outputs=asmama_crawl_output,
                show_progress="full"
            )
            asmama_stop_btn.click(
                lambda: stop_process("asmama_crawl"),
                outputs=asmama_crawl_output
            )

        # 셀럽 검증 탭
        with gr.Tab("⭐ 셀럽 검증"):
            gr.Markdown("### 데이터 검증 및 업로드 변환")

            gr.Markdown("#### 1. 셀럽 정보 필수 검증")
            with gr.Row():
                validate_btn = gr.Button("검증 실행", variant="primary", scale=4)
                validate_stop_btn = gr.Button("중지", variant="stop", scale=1)
            validate_output = gr.Textbox(label="검증 결과", lines=15, max_lines=30, autoscroll=True)

            validate_btn.click(
                validate_celeb,
                outputs=validate_output,
                show_progress="full"
            )
            validate_stop_btn.click(
                lambda: stop_process("validate_celeb"),
                outputs=validate_output
            )

            gr.Markdown("---")

            gr.Markdown("#### 2. 검증된 데이터 업로드 변환")
            with gr.Row():
                upload_btn = gr.Button("업로드 변환 실행", variant="primary", scale=4)
                upload_stop_btn = gr.Button("중지", variant="stop", scale=1)
            upload_output = gr.Textbox(label="변환 결과", lines=15, max_lines=30, autoscroll=True)

            upload_btn.click(
                upload_celeb,
                outputs=upload_output,
                show_progress="full"
            )
            upload_stop_btn.click(
                lambda: stop_process("upload_celeb"),
                outputs=upload_output
            )

    gr.Markdown("---")
    gr.Markdown("### 💡 사용 팁")
    gr.Markdown("""
    - **실시간 로그**: 모든 작업의 진행 상황이 0.5초마다 실시간으로 표시됩니다
    - **중지 버튼**: 각 작업마다 중지 버튼이 있어 언제든지 중단할 수 있습니다
    - **카테고리 필터**: Oliveyoung 크롤링 전 원하는 카테고리만 체크하여 크롤링할 수 있습니다
    - **PostgreSQL 저장**: 체크박스를 선택하면 Excel과 함께 데이터베이스에도 저장됩니다
    - **자동 스크롤**: 새로운 로그가 나타나면 자동으로 스크롤됩니다
    """)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",  # 외부 접속 허용
        server_port=7860,
        share=False,  # True로 설정하면 공개 URL 생성
        inbrowser=True  # 자동으로 브라우저 열기
    )
