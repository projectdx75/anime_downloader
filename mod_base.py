from flask import render_template, request, jsonify
from plugin import PluginModuleBase
import framework
import os, traceback, time, json
from datetime import datetime

class AnimeModuleBase(PluginModuleBase):
    # 업데이트 체크 캐싱 (클래스 레벨)
    _last_update_check = 0
    _latest_version = None
    
    def __init__(self, P, setup_default=None, **kwargs):
        super(AnimeModuleBase, self).__init__(P, **kwargs)
        self.P = P  # Ensure P is available via self.P
        if setup_default:
           self.init_module_settings(setup_default)

    def init_module_settings(self, setup_default):
        try:
            for key, value in setup_default.items():
                if self.P.ModelSetting.get(key) is None:
                    self.P.ModelSetting.set(key, value)
        except Exception as e:
            self.P.logger.error(f"Settings Init Error: {e}")
            self.P.logger.error(traceback.format_exc())

    def process_menu(self, sub, req):
        from framework import F
        try:
            # sub can be None from first_menu
            if sub is None:
                sub = self.first_menu
            
            arg = self.P.ModelSetting.to_dict() if self.P.ModelSetting is not None else {}
            arg["sub"] = self.name
            arg["sub2"] = sub
            arg["package_name"] = self.P.package_name
            arg["module_name"] = self.name 
            arg['path_data'] = F.config['path_data']
            
            # job_id for scheduler
            job_id = f"{self.P.package_name}_{self.name}"
            arg['is_include'] = F.scheduler.is_include(job_id)
            arg['is_running'] = F.scheduler.is_running(job_id)
            # Legacy compatibility for some templates
            arg["scheduler"] = str(arg['is_include'])
            
            code = req.args.get("content_code") or req.args.get("code")
            if sub == "request" and code is not None:
                arg[f"{self.name}_current_code"] = code
            
            # Check template existence
            template_name = f"{self.P.package_name}_{self.name}_{sub}.html"
            return render_template(template_name, arg=arg)

        except Exception as e:
            self.P.logger.error(f"Menu Error: {e}")
            self.P.logger.error(traceback.format_exc())
            return render_template("sample.html", title=f"Error: {e}")

    def process_ajax(self, sub, req):
        try:
            if sub == 'setting_save':
                ret = self.P.ModelSetting.setting_save(req)
                return jsonify(ret)
            
            elif sub == 'scheduler':
                go = req.form['scheduler']
                job_id = f"{self.P.package_name}_{self.name}"
                if go == 'true':
                    framework.scheduler.manage_process(job_id, 'sched', {'sub': self.name})
                else:
                    framework.scheduler.manage_process(job_id, 'cancel', None)
                return jsonify(go)

            elif sub in ['immediately_execute', 'one_execute']:
                job_id = f"{self.P.package_name}_{self.name}"
                framework.scheduler.manage_process(job_id, 'execute', {'sub': self.name})
                return jsonify({'ret': 'success', 'msg': '작업을 시작합니다.'})
            
            elif sub == 'reset_db':
                return jsonify(self.reset_db())

            elif sub == 'browse_dir':
                # Folder Browser Logic (Matches UI expectation)
                path = req.form.get('path')
                if not path:
                    path = '/'
                
                current_path = os.path.abspath(path)
                if not os.path.exists(current_path):
                    current_path = '/'
                
                parent_path = os.path.dirname(current_path)
                if parent_path == current_path:
                    parent_path = None
                
                dirs = []
                try:
                    for name in os.listdir(current_path):
                        full_path = os.path.join(current_path, name)
                        if os.path.isdir(full_path) and not name.startswith('.'):
                            dirs.append({'name': name, 'path': full_path})
                    
                    dirs.sort(key=lambda x: x['name'])
                    return jsonify({'ret': 'success', 'directories': dirs, 'current_path': current_path, 'parent_path': parent_path})
                except Exception as e:
                    return jsonify({'ret': 'fail', 'error': str(e)})

            elif sub == 'queue_command':
                cmd = request.form.get('command')
                if not cmd:
                    cmd = request.args.get('command')
                entity_id_str = request.form.get('entity_id') or request.args.get('entity_id')
                entity_id = int(entity_id_str) if entity_id_str else -1
                ret = self.queue.command(cmd, entity_id) if self.queue else {'ret': 'fail', 'log': 'No queue'}
                return jsonify(ret)
            
            elif sub == 'entity_list':
                return jsonify(self.queue.get_entity_list())
            
            elif sub == 'add_whitelist':
                 # Common whitelist addition
                data = req.get_json() if req.is_json else req.form
                data_code = data.get('data_code')
                if hasattr(self, 'add_whitelist'):
                    return self.add_whitelist(data_code)
                else:
                     return jsonify({'ret': False, 'log': 'Not implemented'})
            
            elif sub == 'command':
                command = request.form.get('command') or request.args.get('command')
                arg1 = request.form.get('arg1') or request.args.get('arg1')
                arg2 = request.form.get('arg2') or request.args.get('arg2')
                arg3 = request.form.get('arg3') or request.args.get('arg3')
                return self.process_command(command, arg1, arg2, arg3, req)

            elif sub == 'self_update':
                # 자가 업데이트 (Git Pull) 및 모듈 리로드
                try:
                    import subprocess
                    plugin_path = os.path.dirname(os.path.dirname(__file__)) if '__file__' in dir() else os.path.dirname(__file__)
                    # 실제 플러그인 루트 디렉토리
                    plugin_path = os.path.dirname(__file__)
                    self.P.logger.info(f"애니 다운로더 자가 업데이트 시작: {plugin_path}")
                    
                    cmd = ['git', '-C', plugin_path, 'pull']
                    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    stdout, stderr = process.communicate()
                    
                    if process.returncode != 0:
                        raise Exception(f"Git pull 실패: {stderr}")
                    
                    self.P.logger.info(f"Git pull 결과: {stdout}")
                    
                    # 모듈 리로드
                    self.reload_plugin()
                    
                    return jsonify({'ret': 'success', 'msg': f"업데이트 및 리로드 완료!<br><pre>{stdout}</pre>", 'data': stdout})
                except Exception as e:
                    self.P.logger.error(f"자가 업데이트 중 오류: {str(e)}")
                    self.P.logger.error(traceback.format_exc())
                    return jsonify({'ret': 'danger', 'msg': f"업데이트 실패: {str(e)}"})

            elif sub == 'check_update':
                force = req.form.get('force') == 'true'
                return jsonify({'ret': 'success', 'data': self.get_update_info(force=force)})

            return jsonify({'ret': 'fail', 'log': f"Unknown sub: {sub}"})

        except Exception as e:
            self.P.logger.error(f"AJAX Error: {e}")
            self.P.logger.error(traceback.format_exc())
            return jsonify({'ret': 'fail', 'log': str(e)})

    def process_command(self, command, arg1, arg2, arg3, req):
        try:
            if not command:
                return jsonify({"ret": "fail", "log": "No command specified"})
                
            if command == "list":
                ret = self.queue.get_entity_list() if self.queue else []
                return jsonify(ret)
            elif command == "stop":
                entity_id = int(arg1) if arg1 else -1
                result = self.queue.command("cancel", entity_id) if self.queue else {"ret": "error"}
                return jsonify(result)
            elif command == "remove":
                entity_id = int(arg1) if arg1 else -1
                result = self.queue.command("remove", entity_id) if self.queue else {"ret": "error"}
                return jsonify(result)
            elif command in ["reset", "delete_completed"]:
                result = self.queue.command(command, 0) if self.queue else {"ret": "error"}
                return jsonify(result)
            
            return jsonify({"ret": "fail", "log": f"Unknown command: {command}"})
        except Exception as e:
            self.P.logger.error(f"process_command Error: {e}")
            self.P.logger.error(traceback.format_exc())
            return jsonify({'ret': 'fail', 'log': str(e)})

    def socketio_callback(self, refresh_type, data):
        """
        socketio를 통해 클라이언트에 상태 업데이트 전송
        refresh_type: 'add', 'status', 'last', 'list_refresh' 등
        data: entity.as_dict() 데이터 또는 리스트 갱신용 빈 문자열
        """
        try:
            from framework import socketio
            
            # /package_name/module_name/queue 네임스페이스로 emit
            namespace = f"/{self.P.package_name}/{self.name}/queue"
            
            # 큐 페이지 소켓에 직접 emit
            socketio.emit(refresh_type, data, namespace=namespace)
            
        except Exception as e:
            self.P.logger.error(f"socketio_callback error: {e}")

    def reset_db(self):
        try:
            # Drop tables logic or delete all rows
            # This requires access to specific Models.
            # Child class should implement or pass Models?
            # Or use self.web_list_model if set
            if self.web_list_model:
                framework.db.session.query(self.web_list_model).delete()
            
            # Delete queue items?
            # ...
            framework.db.session.commit()
            return {'ret': 'success', 'msg': 'DB가 초기화되었습니다.'}
        except Exception as e:
            return {'ret': 'fail', 'msg': str(e)}

    def get_update_info(self, force=False):
        """GitHub에서 최신 버전 정보 가져오기 (캐싱 활용)"""
        import requests
        now = time.time()
        
        # 실제 로컬 파일에서 현재 버전 읽기
        current_version = self.P.plugin_info.get('version', '0.0.0')
        try:
            info_path = os.path.join(os.path.dirname(__file__), 'info.yaml')
            if os.path.exists(info_path):
                import yaml
                with open(info_path, 'r', encoding='utf-8') as f:
                    local_info = yaml.safe_load(f)
                    current_version = str(local_info.get('version', current_version))
        except: pass

        # 1시간마다 체크 (force=True면 즉시)
        if not force and AnimeModuleBase._latest_version and (now - AnimeModuleBase._last_update_check < 3600):
            return {
                'current': current_version,
                'latest': AnimeModuleBase._latest_version,
                'has_update': self._is_newer(AnimeModuleBase._latest_version, current_version)
            }
            
        try:
            url = "https://raw.githubusercontent.com/projectdx75/anime_downloader/master/info.yaml"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                import yaml
                data = yaml.safe_load(res.text)
                AnimeModuleBase._latest_version = str(data.get('version', ''))
                AnimeModuleBase._last_update_check = now
                
                return {
                    'current': current_version,
                    'latest': AnimeModuleBase._latest_version,
                    'has_update': self._is_newer(AnimeModuleBase._latest_version, current_version)
                }
        except Exception as e:
            self.P.logger.error(f"Update check failed: {e}")
            
        return {
            'current': current_version,
            'latest': AnimeModuleBase._latest_version or current_version,
            'has_update': False
        }

    def _is_newer(self, latest, current):
        """버전 비교 (0.7.8 vs 0.7.7)"""
        if not latest or not current: return False
        try:
            l_parts = [int(p) for p in latest.split('.')]
            c_parts = [int(p) for p in current.split('.')]
            return l_parts > c_parts
        except:
            return latest != current

    def reload_plugin(self):
        """플러그인 모듈 핫 리로드"""
        import sys
        import importlib
        
        try:
            package_name = self.P.package_name
            self.P.logger.info(f"플러그인 리로드 시작: {package_name}")
            
            # 관련 모듈 찾기 및 리로드
            modules_to_reload = []
            for module_name in list(sys.modules.keys()):
                if module_name.startswith(package_name):
                    modules_to_reload.append(module_name)
            
            # 의존성 역순으로 정렬 (깊은 모듈 먼저)
            modules_to_reload.sort(key=lambda x: x.count('.'), reverse=True)
            
            for module_name in modules_to_reload:
                try:
                    module = sys.modules[module_name]
                    importlib.reload(module)
                    self.P.logger.debug(f"Reloaded: {module_name}")
                except Exception as e:
                    self.P.logger.warning(f"Failed to reload {module_name}: {e}")
            
            self.P.logger.info(f"플러그인 모듈 [{package_name}] 리로드 완료")
            return True
        except Exception as e:
            self.P.logger.error(f"모듈 리로드 중 실패: {str(e)}")
            self.P.logger.error(traceback.format_exc())
            return False
