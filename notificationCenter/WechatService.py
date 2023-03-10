from grpc.aio import ServicerContext
from grpc import StatusCode
from httpx import AsyncClient

from _321CQU.service import ServiceEnum
from _321CQU.tools.httpServiceManager import HttpServiceManager
from _321CQU.sql_helper import DatabaseConfig

from micro_services_protobuf.notification_center import service_pb2_grpc as notification_grpc
from micro_services_protobuf.notification_center import wechat_pb2 as wechat_model
from micro_services_protobuf import common_pb2 as common_model
from micro_services_protobuf.protobuf_enum.notification_center import NotificationEvent

from notificationCenter.subscribe import handle_subscribe_update
from utils.sqlManager import NCSqlManager
from utils.tools.configManager import ConfigReader


async def _update_subscribe_table(openid: str, event: NotificationEvent, is_subscribe: bool, context: ServicerContext):
    async with NCSqlManager().cursor(DatabaseConfig.Notification) as cursor:
        await cursor.execute('select uid from Openid where openid = %s', (openid,))
        uid = await cursor.fetchone()
        if uid is None:
            await context.abort(code=StatusCode.UNAVAILABLE, details='无法查询到此用户')
        else:
            uid = uid[0]

    await handle_subscribe_update(uid, event, is_subscribe)


class WechatService(notification_grpc.WechatServicer):
    async def SetUserOpenId(self, request: wechat_model.SetUserOpenIdRequest, context: ServicerContext):
        async with AsyncClient(timeout=10) as client:
            res = await client.get(HttpServiceManager().host(ServiceEnum.WechatManager) + f"/openid/{request.code}",
                                   params={'token': ConfigReader().get_config('WechatMiniAppSetting', 'secret')})
            openid = res.text

        async with NCSqlManager().cursor(DatabaseConfig.Notification) as cursor:
            await cursor.execute('insert into Openid (uid, openid) VALUE (%s, %s) on duplicate key update '
                                 'Openid.openid = openid', (request.uid, openid))

        return common_model.DefaultResponse(msg="success")

    async def HandleWechatServerEvent(self, request: wechat_model.HandleWechatServerEventRequest, context):
        if request.template_id == ConfigReader().get_config('WechatMiniAppSetting', 'score_template'):
            await _update_subscribe_table(request.openid, NotificationEvent.ScoreQuery, request.is_accept, context)

        return common_model.DefaultResponse(msg="success")
