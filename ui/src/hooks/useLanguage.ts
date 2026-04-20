import { app } from "../utils/comfyapp"
import showcases from '../../../public/showcase/showcase.json';
import showcases_en from '../../../public/showcase/showcase_en.json';
import { useMemo } from "react";

const STAR_NUM = 3000

const useLanguage = () => {
    const language = app.extensionManager.setting.get('Comfy.Locale')

    const languageData = useMemo(() => {
        let showcase_title = ''
        let showcase_subtitle = ''
        let showcase_list = showcases_en
        let apikeymodel_title = ''
        let chatinput_title = ''
        let startpopview_title = ''
        let startpopview_join = ''
        switch (language) {
          case 'zh':
            showcase_title = '欢迎使用ComfyUI Copilot!'
            showcase_subtitle = `已有 ${STAR_NUM}+ 开发者加入🚀，您的Star是我们持续维护和升级的动力， 👉🏻立即Star。`
            showcase_list = showcases
            apikeymodel_title = '🌟 免费羊毛可持续薅，点个Star服务器不跑路！每个Star都是我们续命的氧气！'
            chatinput_title = '您的Star=我们的动力'
            startpopview_title = `加入我们由 ${STAR_NUM}+ 位 Star 支持者组成的大家庭 \n 您的 Star 让我们更强大！`
            startpopview_join = '点赞加入我们！'
            break;
          case 'en':
          default:
            showcase_title = 'Welcome to ComfyUI Copilot!'
            showcase_subtitle = `${STAR_NUM}+ developers joined🚀, Star us to support continuous updates, 👉🏻Star now.`
            showcase_list = showcases_en
            apikeymodel_title = '💖 Every ⭐ is our lifeline! Tap that star button to keep the magic alive!'
            chatinput_title = 'Your Star = Our Power'
            startpopview_title = `Join our family of ${STAR_NUM}+ Star supporiters \n Your Star makes us stronger!`
            startpopview_join = 'Join Us! Star Now!'
            break;
        }
        return {
          showcase_title,
          showcase_subtitle,
          showcase_list,
          apikeymodel_title,
          chatinput_title,
          startpopview_title,
          startpopview_join
        };
    }, [language])

    return languageData
}

export default useLanguage