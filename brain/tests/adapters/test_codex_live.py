import asyncio
import json
from functools import wraps
from pathlib import Path

import pytest

from milo.adapters.harness.codex_live import CodexLiveModel, CodexLiveOptions, content
from milo.core.ports import LiveModel
from milo.core.registry import ConfigError
from milo.core.types import HarnessError, Usage


def run_async(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return wrapped


FAKE = r'''
import json, os, sys, threading, time
if os.environ.get('CODEX_TEST_STARTUP_ERROR'):
    print('Error: unsupported chat configuration',file=sys.stderr,flush=True)
    sys.exit(2)
def emit(obj):
    print(json.dumps(obj), flush=True)
def result(ident, obj):
    emit({'id': ident, 'result': obj})
def event(method, **params):
    emit({'method': method, 'params': {'threadId':'thread-1', **params}})
for raw in sys.stdin:
    msg=json.loads(raw)
    with open(os.environ['CODEX_TEST_LOG'], 'a', encoding='utf-8') as f:
        f.write(json.dumps(msg)+'\n')
    method=msg.get('method')
    if method=='initialize':
        result(msg['id'], {})
    elif method=='thread/start':
        p=msg['params']
        result(msg['id'], {'thread':{'id':'thread-1'},'approvalPolicy':'on-request',
            'sandbox':{'type':'readOnly','networkAccess':False}})
    elif method=='turn/start':
        text=msg['params']['input'][0]['text']
        result(msg['id'], {'turn':{'id':text}})
        if text=='hang':
            continue
        if text=='die':
            sys.exit(2)
        if text=='approval':
            emit({'id':'approval-1','method':'item/fileChange/requestApproval','params':{}})
            continue
        if text=='unknownrequest':
            emit({'id':'tool-1','method':'item/tool/call','params':{}})
            continue
        if text=='tool':
            event('item/started',turnId=text,item={'type':'fileChange'})
            continue
        if text=='failed':
            event('turn/completed',turn={'id':text,'status':'failed','error':{'message':'no account'}})
            continue
        event('item/agentMessage/delta',turnId=text,delta='Hello ')
        event('item/agentMessage/delta',turnId=text,delta=text)
        event('thread/tokenUsage/updated',turnId=text,tokenUsage={'last':{'inputTokens':12,'cachedInputTokens':8,'outputTokens':2}})
        event('turn/completed',turn={'id':text,'status':'completed'})
    elif method=='turn/interrupt':
        result(msg['id'], {})
        event('turn/completed',turn={'id':msg['params']['turnId'],'status':'interrupted'})
'''


@pytest.fixture
def model(tmp_path, monkeypatch):
    binary = tmp_path / 'codex.py'
    binary.write_text(FAKE, encoding='utf-8')
    monkeypatch.setenv('CODEX_TEST_LOG', str(tmp_path / 'rpc.jsonl'))
    # No credential file is needed or read by the fake CLI.
    return CodexLiveModel(str(binary), tmp_path / 'chat', login_from=tmp_path / 'login')


def calls(model):
    return [json.loads(x) for x in (model.workdir.parent / 'rpc.jsonl').read_text(encoding='utf-8').splitlines()]


async def answer(model, text):
    return ''.join([part async for part in model.turn(text)])


@run_async
async def test_streaming_conversation_and_usage(model):
    assert isinstance(model, LiveModel)
    await model.start('Milo’s system prompt')
    try:
        assert await answer(model, 'one') == 'Hello one'
        assert await answer(model, 'two') == 'Hello two'
        assert model.last_usage == Usage(input_tokens=12, cached_input_tokens=8, output_tokens=2)
        messages = calls(model)
        assert sum(m.get('method') == 'thread/start' for m in messages) == 1
        start = next(m['params'] for m in messages if m.get('method') == 'thread/start')
        assert 'Milo’s system prompt' in start['baseInstructions']
        assert start['approvalPolicy'] == 'on-request'
        assert start['sandbox'] == 'read-only'
        assert start['ephemeral'] is True and start['dynamicTools'] == [] and start['environments'] == []
        turn = next(m['params'] for m in messages if m.get('method') == 'turn/start')
        assert turn['sandboxPolicy'] == {'type':'readOnly', 'networkAccess':False}
        config = (model.workdir / 'home/config.toml').read_text(encoding='utf-8')
        import tomllib
        parsed = tomllib.loads(config)
        assert parsed['web_search'] == 'disabled'
        assert parsed['features']['shell_tool'] is False
        assert parsed['features']['apps'] is False
        assert 'mcp_servers' not in parsed
    finally:
        await model.close()


@pytest.mark.parametrize('text', ['approval', 'unknownrequest', 'tool'])
@run_async
async def test_tool_attempts_are_refused_and_session_closed(model, text):
    await model.start('Text only')
    with pytest.raises(HarnessError, match='tool|refused'):
        await answer(model, text)
    assert model._rpc is None
    if text == 'approval':
        assert any(m.get('id') == 'approval-1' and m.get('result') == {'decision':'cancel'} for m in calls(model))
    if text == 'unknownrequest':
        assert any(m.get('id') == 'tool-1' and 'error' in m for m in calls(model))


@run_async
async def test_interrupt_preserves_session_for_next_turn(model):
    await model.start('Text only')
    try:
        task = asyncio.create_task(answer(model, 'hang'))
        for _ in range(100):
            if model._turn_id:
                break
            await asyncio.sleep(.01)
        await model.interrupt()
        assert await asyncio.wait_for(task, 2) == ''
        assert await answer(model, 'after') == 'Hello after'
    finally:
        await model.close()


@pytest.mark.parametrize('text', ['die', 'failed', 'hang'])
@run_async
async def test_failed_stream_is_bounded_without_replay(model, text):
    await model.start('Text only')
    model.stall_timeout_s = .05
    with pytest.raises(HarnessError):
        await asyncio.wait_for(answer(model, text), 3)
    assert model._rpc is None
    assert sum(m.get('method') == 'turn/start' for m in calls(model)) == 1


@run_async
async def test_cancelled_generator_interrupts_and_keeps_conversation(model):
    await model.start('Text only')
    proc = model._rpc.proc
    task = asyncio.create_task(answer(model, 'hang'))
    await asyncio.sleep(.03)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    try:
        assert proc.returncode is None
        assert await answer(model, 'after-cancel') == 'Hello after-cancel'
    finally:
        await model.close()
    assert proc.returncode is not None


def test_image_is_inline_and_missing_image_fails(tmp_path):
    image = tmp_path / 'screen.png'
    image.write_bytes(b'png')
    blocks = content('look', [image])
    assert blocks == [{'type':'text','text':'look'}, {'type':'image','url':'data:image/png;base64,cG5n'}]
    with pytest.raises(HarnessError, match='screenshot'):
        content('look', [tmp_path / 'missing.png'])


def test_options_default_and_validation():
    assert CodexLiveOptions().model == ''
    with pytest.raises(ConfigError):
        CodexLiveOptions(model=1)


@run_async
async def test_startup_error_is_clear_without_disclosing_other_stderr(model, monkeypatch):
    monkeypatch.setenv('CODEX_TEST_STARTUP_ERROR','1')
    with pytest.raises(HarnessError, match='unsupported chat configuration') as error:
        await model.start('Secret prompt that never reaches a turn')
    assert error.value.transient is False
    assert model._rpc is None


@run_async
async def test_rejects_weakened_permissions_before_first_turn(model):
    path = Path(model.binary)
    path.write_text(FAKE.replace("'type':'readOnly'", "'type':'dangerFullAccess'"),encoding='utf-8')
    with pytest.raises(HarnessError, match='read-only permissions'):
        await model.start('Text only')
    assert model._rpc is None
    assert not any(m.get('method') == 'turn/start' for m in calls(model))


